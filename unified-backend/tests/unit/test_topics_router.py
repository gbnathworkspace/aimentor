"""Unit tests for app/routers/topics.py — topic CRUD and messaging endpoints.

Tests cover:
- Create topic (200 with topic data)
- List topics (returns array)
- Get topic by id (200 with topic data)
- Get topic 404 for non-existent
- Rename topic
- Archive topic
- Send message (returns response)
- Authentication required (401 without auth)
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _setup_settings():
    get_settings.cache_clear()
    env = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "MENTORMAN_API_KEY": "test-api-key",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "VOYAGE_API_KEY": "voy-test",
    }
    with patch.dict(os.environ, env, clear=True):
        get_settings()
        yield
    get_settings.cache_clear()


@pytest.fixture
def auth_headers():
    return {"X-User-Id": "user-123", "X-Api-Key": "test-api-key"}


def _sample_topic(**overrides):
    """Return a sample topic document."""
    doc = {
        "topicId": "topic-abc",
        "userId": "user-123",
        "title": "Learning Python",
        "status": "active",
        "mode": None,
        "createdAt": "2026-06-01T00:00:00",
        "lastActiveAt": "2026-06-01T00:00:00",
        "messages": [],
        "compactionCount": 0,
        "metadata": {"totalMessageCount": 0, "currentTokenEstimate": 0},
        "version": 0,
    }
    doc.update(overrides)
    return doc


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestCreateTopic:
    @pytest.mark.asyncio
    async def test_create_topic_success(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.create_topic = AsyncMock(return_value=_sample_topic())

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.post(
                    "/api/topics",
                    headers=auth_headers,
                    json={"title": "Learning Python"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["topicId"] == "topic-abc"
        assert data["title"] == "Learning Python"
        mock_service.create_topic.assert_awaited_once_with("user-123", "Learning Python")

    @pytest.mark.asyncio
    async def test_create_topic_empty_title_422(self, auth_headers):
        """Pydantic rejects empty title with 422."""
        from app.main import app

        async with await _client(app) as client:
            resp = await client.post(
                "/api/topics",
                headers=auth_headers,
                json={"title": ""},
            )

        assert resp.status_code == 422


class TestListTopics:
    @pytest.mark.asyncio
    async def test_list_topics_returns_array(self, auth_headers):
        topics_list = [
            {"topicId": "t1", "title": "Topic 1", "status": "active", "messagePreview": ""},
            {"topicId": "t2", "title": "Topic 2", "status": "active", "messagePreview": "hello"},
        ]
        mock_service = AsyncMock()
        mock_service.list_topics = AsyncMock(return_value=topics_list)

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get("/api/topics", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["topicId"] == "t1"

    @pytest.mark.asyncio
    async def test_list_topics_empty(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.list_topics = AsyncMock(return_value=[])

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get("/api/topics", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetTopic:
    @pytest.mark.asyncio
    async def test_get_topic_success(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.get_topic = AsyncMock(return_value=_sample_topic())

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get("/api/topic/topic-abc", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["topicId"] == "topic-abc"
        assert data["title"] == "Learning Python"
        mock_service.get_topic.assert_awaited_once_with("topic-abc", "user-123")

    @pytest.mark.asyncio
    async def test_get_topic_not_found(self, auth_headers):
        """Returns 404 for non-existent topic (same as unauthorized)."""
        mock_service = AsyncMock()
        mock_service.get_topic = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Topic not found")
        )

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get("/api/topic/nonexistent", headers=auth_headers)

        assert resp.status_code == 404


class TestRenameTopic:
    @pytest.mark.asyncio
    async def test_rename_topic_success(self, auth_headers):
        updated = _sample_topic(title="Advanced Python")
        mock_service = AsyncMock()
        mock_service.rename_topic = AsyncMock(return_value=updated)

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.patch(
                    "/api/topic/topic-abc",
                    headers=auth_headers,
                    json={"title": "Advanced Python"},
                )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Advanced Python"
        mock_service.rename_topic.assert_awaited_once_with(
            "topic-abc", "user-123", "Advanced Python"
        )

    @pytest.mark.asyncio
    async def test_rename_topic_not_found(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.rename_topic = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Topic not found")
        )

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.patch(
                    "/api/topic/nonexistent",
                    headers=auth_headers,
                    json={"title": "New Title"},
                )

        assert resp.status_code == 404


class TestArchiveTopic:
    @pytest.mark.asyncio
    async def test_archive_topic_success(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.archive_topic = AsyncMock(return_value=None)

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.post("/api/topic/topic-abc/archive", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "archived"
        assert data["topicId"] == "topic-abc"
        mock_service.archive_topic.assert_awaited_once_with("topic-abc", "user-123")

    @pytest.mark.asyncio
    async def test_archive_topic_not_found(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.archive_topic = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Topic not found")
        )

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.post("/api/topic/nonexistent/archive", headers=auth_headers)

        assert resp.status_code == 404


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_success(self, auth_headers):
        mock_chat = AsyncMock()
        mock_chat.handle_message = AsyncMock(
            return_value={"response": "Hello! I can help you with Python."}
        )

        with patch("app.routers.topics._chat_service", mock_chat):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.post(
                    "/api/topic/topic-abc/message",
                    headers=auth_headers,
                    json={"content": "Help me learn Python", "mode": "topic"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hello! I can help you with Python."
        mock_chat.handle_message.assert_awaited_once_with(
            "topic-abc", "user-123", "Help me learn Python", "topic"
        )

    @pytest.mark.asyncio
    async def test_send_message_empty_content_422(self, auth_headers):
        """Pydantic rejects empty content."""
        from app.main import app

        async with await _client(app) as client:
            resp = await client.post(
                "/api/topic/topic-abc/message",
                headers=auth_headers,
                json={"content": ""},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_send_message_topic_not_found(self, auth_headers):
        mock_chat = AsyncMock()
        mock_chat.handle_message = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Topic not found")
        )

        with patch("app.routers.topics._chat_service", mock_chat):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.post(
                    "/api/topic/nonexistent/message",
                    headers=auth_headers,
                    json={"content": "Hello"},
                )

        assert resp.status_code == 404


class TestAuthenticationRequired:
    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self):
        """All endpoints require authentication — 401 without credentials."""
        from app.main import app

        async with await _client(app) as client:
            # POST /api/topics
            resp = await client.post("/api/topics", json={"title": "Test"})
            assert resp.status_code == 401

            # GET /api/topics
            resp = await client.get("/api/topics")
            assert resp.status_code == 401

            # GET /api/topic/:id
            resp = await client.get("/api/topic/some-id")
            assert resp.status_code == 401

            # PATCH /api/topic/:id
            resp = await client.patch("/api/topic/some-id", json={"title": "New"})
            assert resp.status_code == 401

            # POST /api/topic/:id/archive
            resp = await client.post("/api/topic/some-id/archive")
            assert resp.status_code == 401

            # POST /api/topic/:id/message
            resp = await client.post(
                "/api/topic/some-id/message", json={"content": "Hello"}
            )
            assert resp.status_code == 401
