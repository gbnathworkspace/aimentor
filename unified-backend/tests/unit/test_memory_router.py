"""Unit tests for app/routers/memory.py — Memory episodes endpoints."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _setup_settings():
    """Ensure get_settings returns predictable config for all tests."""
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


@pytest.fixture
def mock_sessions_col():
    """Provide a mocked sessions_col with async methods."""
    col = MagicMock()
    col.find = MagicMock()
    col.find_one = AsyncMock()
    col.delete_one = AsyncMock()
    col.aggregate = MagicMock()
    return col


class TestSearchEpisodes:
    """POST /api/memory/episodes/search — vector search."""

    @pytest.mark.asyncio
    async def test_search_returns_matching_episodes(self, auth_headers, mock_sessions_col):
        episodes = [
            {
                "session_id": "sess-1",
                "title": "Python Basics",
                "summary": "Learned about variables",
                "topic": "python",
                "date": "2024-01-15",
                "skill_update": {"current_level": "intermediate"},
                "score": 0.92,
            }
        ]
        agg_cursor = MagicMock()
        agg_cursor.to_list = AsyncMock(return_value=episodes)
        mock_sessions_col.aggregate = MagicMock(return_value=agg_cursor)

        mock_embed = AsyncMock(return_value=[0.1] * 1024)

        with (
            patch("app.routers.memory.sessions_col", return_value=mock_sessions_col),
            patch("app.routers.memory.embed_text", mock_embed),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/memory/episodes/search",
                    headers=auth_headers,
                    json={"query": "python variables", "limit": 3},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "sess-1"
        assert data[0]["score"] == 0.92

    @pytest.mark.asyncio
    async def test_search_with_topic_filter(self, auth_headers, mock_sessions_col):
        agg_cursor = MagicMock()
        agg_cursor.to_list = AsyncMock(return_value=[])
        mock_sessions_col.aggregate = MagicMock(return_value=agg_cursor)

        mock_embed = AsyncMock(return_value=[0.1] * 1024)

        with (
            patch("app.routers.memory.sessions_col", return_value=mock_sessions_col),
            patch("app.routers.memory.embed_text", mock_embed),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/memory/episodes/search",
                    headers=auth_headers,
                    json={"query": "loops", "limit": 5, "topic": "python"},
                )

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_embedding_fails(self, auth_headers, mock_sessions_col):
        mock_embed = AsyncMock(return_value=[])

        with (
            patch("app.routers.memory.sessions_col", return_value=mock_sessions_col),
            patch("app.routers.memory.embed_text", mock_embed),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/memory/episodes/search",
                    headers=auth_headers,
                    json={"query": "test query"},
                )

        assert resp.status_code == 200
        assert resp.json() == []


class TestListEpisodes:
    """GET /api/memory/episodes — paginated list."""

    @pytest.mark.asyncio
    async def test_list_returns_episodes_with_defaults(self, auth_headers, mock_sessions_col):
        episodes = [
            {"session_id": "sess-1", "title": "Session 1", "topic": "python", "date": "2024-01-15"},
            {"session_id": "sess-2", "title": "Session 2", "topic": "fastapi", "date": "2024-01-14"},
        ]
        cursor_mock = MagicMock()
        cursor_mock.sort = MagicMock(return_value=cursor_mock)
        cursor_mock.skip = MagicMock(return_value=cursor_mock)
        cursor_mock.limit = MagicMock(return_value=cursor_mock)
        cursor_mock.to_list = AsyncMock(return_value=episodes)
        mock_sessions_col.find = MagicMock(return_value=cursor_mock)

        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/memory/episodes", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_list_with_pagination_params(self, auth_headers, mock_sessions_col):
        cursor_mock = MagicMock()
        cursor_mock.sort = MagicMock(return_value=cursor_mock)
        cursor_mock.skip = MagicMock(return_value=cursor_mock)
        cursor_mock.limit = MagicMock(return_value=cursor_mock)
        cursor_mock.to_list = AsyncMock(return_value=[])
        mock_sessions_col.find = MagicMock(return_value=cursor_mock)

        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/memory/episodes?limit=10&offset=5",
                    headers=auth_headers,
                )

        assert resp.status_code == 200
        # Verify pagination was applied
        cursor_mock.skip.assert_called_with(5)
        cursor_mock.limit.assert_called_with(10)

    @pytest.mark.asyncio
    async def test_list_with_topic_filter(self, auth_headers, mock_sessions_col):
        cursor_mock = MagicMock()
        cursor_mock.sort = MagicMock(return_value=cursor_mock)
        cursor_mock.skip = MagicMock(return_value=cursor_mock)
        cursor_mock.limit = MagicMock(return_value=cursor_mock)
        cursor_mock.to_list = AsyncMock(return_value=[])
        mock_sessions_col.find = MagicMock(return_value=cursor_mock)

        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/memory/episodes?topic=python",
                    headers=auth_headers,
                )

        assert resp.status_code == 200
        # Verify the find was called with topic filter
        call_args = mock_sessions_col.find.call_args
        assert call_args[0][0]["topic"] == "python"

    @pytest.mark.asyncio
    async def test_list_rejects_invalid_limit(self, auth_headers, mock_sessions_col):
        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/memory/episodes?limit=200",
                    headers=auth_headers,
                )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_rejects_negative_offset(self, auth_headers, mock_sessions_col):
        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/memory/episodes?offset=-1",
                    headers=auth_headers,
                )

        assert resp.status_code == 422


class TestDeleteEpisode:
    """DELETE /api/memory/episodes/{session_id} — remove an episode."""

    @pytest.mark.asyncio
    async def test_delete_owned_episode(self, auth_headers, mock_sessions_col):
        mock_sessions_col.find_one = AsyncMock(
            return_value={"session_id": "sess-1", "user_id": "user-123"}
        )
        mock_sessions_col.delete_one = AsyncMock()

        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete(
                    "/api/memory/episodes/sess-1",
                    headers=auth_headers,
                )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_sessions_col.delete_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_404_for_missing_episode(self, auth_headers, mock_sessions_col):
        mock_sessions_col.find_one = AsyncMock(return_value=None)

        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete(
                    "/api/memory/episodes/nonexistent",
                    headers=auth_headers,
                )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_returns_403_for_other_users_episode(self, auth_headers, mock_sessions_col):
        mock_sessions_col.find_one = AsyncMock(
            return_value={"session_id": "sess-1", "user_id": "other-user"}
        )

        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete(
                    "/api/memory/episodes/sess-1",
                    headers=auth_headers,
                )

        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"].lower()


class TestAuthEnforcement:
    """Verify auth is enforced on all memory endpoints."""

    @pytest.mark.asyncio
    async def test_search_without_auth_returns_401(self, mock_sessions_col):
        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/memory/episodes/search",
                    json={"query": "test"},
                )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_without_auth_returns_401(self, mock_sessions_col):
        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/memory/episodes")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_without_auth_returns_401(self, mock_sessions_col):
        with patch("app.routers.memory.sessions_col", return_value=mock_sessions_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete("/api/memory/episodes/sess-1")

        assert resp.status_code == 401
