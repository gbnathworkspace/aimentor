"""Unit tests for app/routers/sessions.py — session list, update (title), delete.

Covers the production-hardening fixes:
- list_sessions filters to live chat sessions (messages exists) and sorts by
  updated_at descending (most-recently-active first).
- PATCH can update the title.
- DELETE removes a session with ownership checks.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


def _full_session(**over):
    doc = {
        "session_id": "s1",
        "user_id": "user-123",
        "title": "New session",
        "mode": "topic",
        "topic": "graphs",
        "status": "active",
        "messages": [],
        "tags": [],
        "summary": None,
        "created_at": "2026-06-01T00:00:00+00:00",
        "updated_at": "2026-06-01T00:00:00+00:00",
    }
    doc.update(over)
    return doc


@pytest.fixture
def mock_col():
    col = MagicMock()
    col.find = MagicMock()
    col.find_one = AsyncMock()
    col.update_one = AsyncMock()
    col.delete_one = AsyncMock()
    return col


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestListSessions:
    @pytest.mark.asyncio
    async def test_filters_live_sessions_and_sorts_by_updated_at(self, auth_headers, mock_col):
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[_full_session()])
        mock_col.find = MagicMock(return_value=cursor)

        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.get("/api/sessions?limit=30", headers=auth_headers)

        assert resp.status_code == 200
        # Query filters to docs that have a messages array (excludes episodic summaries)
        find_args = mock_col.find.call_args[0][0]
        assert find_args.get("messages") == {"$exists": True}
        assert find_args.get("user_id") == "user-123"
        # Sorted by updated_at descending (most-recently-active first)
        cursor.sort.assert_called_once_with("updated_at", -1)

    @pytest.mark.asyncio
    async def test_empty_list(self, auth_headers, mock_col):
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[])
        mock_col.find = MagicMock(return_value=cursor)

        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.get("/api/sessions", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateSessionTitle:
    @pytest.mark.asyncio
    async def test_patch_updates_title(self, auth_headers, mock_col):
        mock_col.find_one = AsyncMock(side_effect=[
            _full_session(),  # ownership lookup
            _full_session(title="How do I balance a BST?"),  # post-update read
        ])
        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.patch(
                    "/api/sessions/s1",
                    headers=auth_headers,
                    json={"title": "How do I balance a BST?"},
                )
        assert resp.status_code == 200
        assert resp.json()["title"] == "How do I balance a BST?"
        # title was part of the $set payload
        set_payload = mock_col.update_one.call_args[0][1]["$set"]
        assert set_payload["title"] == "How do I balance a BST?"

    @pytest.mark.asyncio
    async def test_patch_404_when_missing(self, auth_headers, mock_col):
        mock_col.find_one = AsyncMock(return_value=None)
        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.patch("/api/sessions/x", headers=auth_headers, json={"title": "t"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_403_when_not_owned(self, auth_headers, mock_col):
        mock_col.find_one = AsyncMock(return_value=_full_session(user_id="someone-else"))
        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.patch("/api/sessions/s1", headers=auth_headers, json={"title": "t"})
        assert resp.status_code == 403


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_ok(self, auth_headers, mock_col):
        mock_col.find_one = AsyncMock(return_value=_full_session())
        mock_col.delete_one = AsyncMock()
        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.delete("/api/sessions/s1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_col.delete_one.assert_awaited_once_with({"session_id": "s1"})

    @pytest.mark.asyncio
    async def test_delete_404_when_missing(self, auth_headers, mock_col):
        mock_col.find_one = AsyncMock(return_value=None)
        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.delete("/api/sessions/x", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_403_when_not_owned(self, auth_headers, mock_col):
        mock_col.find_one = AsyncMock(return_value=_full_session(user_id="other"))
        with patch("app.routers.sessions.sessions_col", return_value=mock_col):
            from app.main import app
            async with await _client(app) as client:
                resp = await client.delete("/api/sessions/s1", headers=auth_headers)
        assert resp.status_code == 403
