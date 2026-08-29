"""Unit tests for app/routers/skills.py — Skills CRUD endpoints."""

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
def mock_skill_col():
    """Provide a mocked skill_graph_col with async methods."""
    col = MagicMock()
    col.find = MagicMock()
    col.find_one = AsyncMock()
    col.update_one = AsyncMock()
    col.find_one_and_update = AsyncMock()
    col.delete_one = AsyncMock()
    return col


@pytest.fixture
def app_with_mock_db(mock_skill_col):
    """Create a FastAPI app with mocked database collection."""
    with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
        from app.main import app

        yield app


class TestListSkills:
    """GET /api/skills — list all skill nodes for user."""

    @pytest.mark.asyncio
    async def test_returns_all_skills(self, auth_headers, mock_skill_col):
        skills_data = [
            {"topic": "python", "current_level": "intermediate"},
            {"topic": "fastapi", "current_level": "beginner"},
        ]
        cursor_mock = MagicMock()
        cursor_mock.to_list = AsyncMock(return_value=skills_data)
        mock_skill_col.find = MagicMock(return_value=cursor_mock)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/skills", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["topic"] == "python"
        assert data[1]["topic"] == "fastapi"
        # Verify camelCase field names in response
        assert "currentLevel" in data[0]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_skills(self, auth_headers, mock_skill_col):
        cursor_mock = MagicMock()
        cursor_mock.to_list = AsyncMock(return_value=[])
        mock_skill_col.find = MagicMock(return_value=cursor_mock)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/skills", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetSkill:
    """GET /api/skills/{topic} — get single skill node."""

    @pytest.mark.asyncio
    async def test_returns_skill_by_topic(self, auth_headers, mock_skill_col):
        skill_doc = {"topic": "python", "current_level": "intermediate"}
        mock_skill_col.find_one = AsyncMock(return_value=skill_doc)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/skills/python", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["topic"] == "python"
        # Verify camelCase field names in response
        assert "currentLevel" in resp.json()

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_topic(self, auth_headers, mock_skill_col):
        mock_skill_col.find_one = AsyncMock(return_value=None)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/skills/nonexistent", headers=auth_headers)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestUpsertSkill:
    """POST /api/skills — upsert a skill node."""

    @pytest.mark.asyncio
    async def test_upsert_creates_skill_returns_201(self, auth_headers, mock_skill_col):
        mock_skill_col.update_one = AsyncMock()

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/skills",
                    headers=auth_headers,
                    json={"topic": "python", "currentLevel": "beginner"},
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["topic"] == "python"
        assert data["currentLevel"] == "beginner"
        mock_skill_col.update_one.assert_called_once()


class TestUpdateSkill:
    """PUT /api/skills/{topic} — update a specific skill node."""

    @pytest.mark.asyncio
    async def test_update_returns_updated_skill(self, auth_headers, mock_skill_col):
        updated_doc = {"topic": "python", "current_level": "advanced"}
        mock_skill_col.find_one_and_update = AsyncMock(return_value=updated_doc)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    "/api/skills/python",
                    headers=auth_headers,
                    json={"currentLevel": "advanced"},
                )

        assert resp.status_code == 200
        assert resp.json()["currentLevel"] == "advanced"

    @pytest.mark.asyncio
    async def test_update_returns_404_for_missing_topic(self, auth_headers, mock_skill_col):
        mock_skill_col.find_one_and_update = AsyncMock(return_value=None)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    "/api/skills/nonexistent",
                    headers=auth_headers,
                    json={"currentLevel": "advanced"},
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_400_with_empty_body(self, auth_headers, mock_skill_col):
        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    "/api/skills/python",
                    headers=auth_headers,
                    json={},
                )

        assert resp.status_code == 400
        assert "No fields" in resp.json()["detail"]


class TestDeleteSkill:
    """DELETE /api/skills/{topic} — remove a skill node."""

    @pytest.mark.asyncio
    async def test_delete_returns_ok(self, auth_headers, mock_skill_col):
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        mock_skill_col.delete_one = AsyncMock(return_value=delete_result)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete("/api/skills/python", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_delete_returns_404_for_missing_topic(self, auth_headers, mock_skill_col):
        delete_result = MagicMock()
        delete_result.deleted_count = 0
        mock_skill_col.delete_one = AsyncMock(return_value=delete_result)

        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete("/api/skills/nonexistent", headers=auth_headers)

        assert resp.status_code == 404


class TestAuthEnforcement:
    """Verify auth is enforced on all skills endpoints."""

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self, mock_skill_col):
        with patch("app.routers.skills.skill_graph_col", return_value=mock_skill_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/skills")

        assert resp.status_code == 401
