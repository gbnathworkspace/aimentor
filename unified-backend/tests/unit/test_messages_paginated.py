"""Unit tests for paginated messages endpoint and TopicService.get_messages_paginated.

Tests cover:
- Paginated retrieval returns correct page of messages
- hasMore flag is true when older messages exist
- hasMore flag is false when all messages fit
- skip parameter correctly offsets from end
- Empty topic returns empty list
- 404 for non-existent topic
- limit is clamped to 1-100 range
- API endpoint routes correctly with query params

Requirements: 14.4
"""

import os
from datetime import datetime, timezone
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


def _make_messages(count: int) -> list[dict]:
    """Generate a list of test messages."""
    from datetime import timedelta

    base = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    messages = []
    for i in range(count):
        messages.append({
            "type": "message",
            "id": f"msg-{i}",
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Message {i}",
            "timestamp": base + timedelta(minutes=i),
            "tokenCount": 10,
        })
    return messages


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# --- TopicService.get_messages_paginated unit tests ---


class TestGetMessagesPaginated:
    """Tests for TopicService.get_messages_paginated."""

    @pytest.mark.asyncio
    async def test_returns_most_recent_messages_by_default(self):
        """With skip=0, returns the most recent `limit` messages."""
        from app.services.topic_service import TopicService

        messages = _make_messages(100)
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"messages": messages})

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            result = await service.get_messages_paginated("topic-1", "user-1", limit=50, skip=0)

        assert len(result["messages"]) == 50
        assert result["total"] == 100
        assert result["hasMore"] is True
        # Should be the last 50 messages (index 50-99)
        assert result["messages"][0]["id"] == "msg-50"
        assert result["messages"][-1]["id"] == "msg-99"

    @pytest.mark.asyncio
    async def test_skip_offsets_from_end(self):
        """skip=50 with limit=50 returns messages 0-49."""
        from app.services.topic_service import TopicService

        messages = _make_messages(100)
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"messages": messages})

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            result = await service.get_messages_paginated("topic-1", "user-1", limit=50, skip=50)

        assert len(result["messages"]) == 50
        assert result["total"] == 100
        assert result["hasMore"] is False
        assert result["messages"][0]["id"] == "msg-0"
        assert result["messages"][-1]["id"] == "msg-49"

    @pytest.mark.asyncio
    async def test_has_more_false_when_all_messages_fit(self):
        """Small topic returns all messages with hasMore=False."""
        from app.services.topic_service import TopicService

        messages = _make_messages(10)
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"messages": messages})

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            result = await service.get_messages_paginated("topic-1", "user-1", limit=50, skip=0)

        assert len(result["messages"]) == 10
        assert result["total"] == 10
        assert result["hasMore"] is False

    @pytest.mark.asyncio
    async def test_empty_topic_returns_empty_list(self):
        """Topic with no messages returns empty result."""
        from app.services.topic_service import TopicService

        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"messages": []})

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            result = await service.get_messages_paginated("topic-1", "user-1", limit=50, skip=0)

        assert result["messages"] == []
        assert result["total"] == 0
        assert result["hasMore"] is False

    @pytest.mark.asyncio
    async def test_topic_not_found_raises_404(self):
        """Non-existent topic raises HTTPException 404."""
        from app.services.topic_service import TopicService

        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value=None)

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            with pytest.raises(HTTPException) as exc_info:
                await service.get_messages_paginated("nonexistent", "user-1", limit=50, skip=0)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_skip_beyond_total_returns_empty(self):
        """skip larger than total messages returns empty list."""
        from app.services.topic_service import TopicService

        messages = _make_messages(20)
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"messages": messages})

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            result = await service.get_messages_paginated("topic-1", "user-1", limit=50, skip=30)

        assert result["messages"] == []
        assert result["total"] == 20
        assert result["hasMore"] is False

    @pytest.mark.asyncio
    async def test_limit_clamped_to_max_100(self):
        """Limit values above 100 are clamped to 100."""
        from app.services.topic_service import TopicService

        messages = _make_messages(200)
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value={"messages": messages})

        service = TopicService()
        with patch("app.services.topic_service.topics_col", return_value=mock_col):
            result = await service.get_messages_paginated("topic-1", "user-1", limit=150, skip=0)

        assert len(result["messages"]) == 100


# --- API Endpoint tests ---


class TestGetMessagesPaginatedEndpoint:
    """Tests for GET /api/topic/{topic_id}/messages endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_paginated_messages(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.get_messages_paginated = AsyncMock(
            return_value={
                "messages": [{"id": "msg-1", "content": "Hello"}],
                "total": 100,
                "hasMore": True,
            }
        )

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get(
                    "/api/topic/topic-abc/messages?limit=50&skip=0",
                    headers=auth_headers,
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 100
        assert data["hasMore"] is True
        assert len(data["messages"]) == 1
        mock_service.get_messages_paginated.assert_awaited_once_with(
            "topic-abc", "user-123", limit=50, skip=0
        )

    @pytest.mark.asyncio
    async def test_endpoint_default_params(self, auth_headers):
        """Without query params, defaults to limit=50 skip=0."""
        mock_service = AsyncMock()
        mock_service.get_messages_paginated = AsyncMock(
            return_value={"messages": [], "total": 0, "hasMore": False}
        )

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get(
                    "/api/topic/topic-abc/messages",
                    headers=auth_headers,
                )

        assert resp.status_code == 200
        mock_service.get_messages_paginated.assert_awaited_once_with(
            "topic-abc", "user-123", limit=50, skip=0
        )

    @pytest.mark.asyncio
    async def test_endpoint_404_for_missing_topic(self, auth_headers):
        mock_service = AsyncMock()
        mock_service.get_messages_paginated = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Topic not found")
        )

        with patch("app.routers.topics._topic_service", mock_service):
            from app.main import app

            async with await _client(app) as client:
                resp = await client.get(
                    "/api/topic/nonexistent/messages",
                    headers=auth_headers,
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_endpoint_requires_auth(self):
        """Endpoint returns 401 without authentication."""
        from app.main import app

        async with await _client(app) as client:
            resp = await client.get("/api/topic/topic-abc/messages")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_endpoint_invalid_limit_422(self, auth_headers):
        """limit=0 violates ge=1 constraint and returns 422."""
        from app.main import app

        async with await _client(app) as client:
            resp = await client.get(
                "/api/topic/topic-abc/messages?limit=0",
                headers=auth_headers,
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_negative_skip_422(self, auth_headers):
        """Negative skip violates ge=0 constraint and returns 422."""
        from app.main import app

        async with await _client(app) as client:
            resp = await client.get(
                "/api/topic/topic-abc/messages?skip=-1",
                headers=auth_headers,
            )

        assert resp.status_code == 422
