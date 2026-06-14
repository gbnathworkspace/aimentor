"""Unit tests for app/routers/session_end.py — POST /api/session/end endpoint."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _setup_settings():
    """Ensure get_settings returns predictable values for all tests."""
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
    return {
        "X-User-Id": "test-user-123",
        "X-Api-Key": "test-api-key",
    }


@pytest.fixture
def valid_request_body():
    return {
        "topic": "python-basics",
        "messages": [
            {"role": "user", "content": "How do I use list comprehensions?"},
            {"role": "assistant", "content": "List comprehensions provide a concise way to create lists..."},
        ],
    }


@pytest.fixture
def mock_session_end_result():
    return {
        "session_id": "abc-123-def",
        "title": "Understanding List Comprehensions",
        "summary": "The user learned about Python list comprehensions and their syntax.",
        "skill_update": {"current_level": "intermediate"},
    }


class TestSessionEndEndpoint:
    """Verify POST /api/session/end delegates properly and handles errors."""

    @pytest.mark.asyncio
    async def test_successful_session_end(
        self, auth_headers, valid_request_body, mock_session_end_result
    ):
        """Valid request returns session_id, title, summary, and skill_update."""
        with patch(
            "app.routers.session_end.process_session_end",
            new_callable=AsyncMock,
            return_value=mock_session_end_result,
        ) as mock_process:
            from app.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/session/end",
                    json=valid_request_body,
                    headers=auth_headers,
                )

            assert response.status_code == 200
            body = response.json()
            assert body["session_id"] == "abc-123-def"
            assert body["title"] == "Understanding List Comprehensions"
            assert body["summary"] == "The user learned about Python list comprehensions and their syntax."
            assert body["skill_update"] == {"current_level": "intermediate"}

            # Verify process_session_end was called with correct args
            mock_process.assert_called_once_with(
                "test-user-123",
                "python-basics",
                [
                    {"role": "user", "content": "How do I use list comprehensions?", "timestamp": None},
                    {"role": "assistant", "content": "List comprehensions provide a concise way to create lists...", "timestamp": None},
                ],
            )

    @pytest.mark.asyncio
    async def test_llm_failure_returns_500(self, auth_headers, valid_request_body):
        """When process_session_end raises, endpoint returns HTTP 500."""
        with patch(
            "app.routers.session_end.process_session_end",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API unavailable"),
        ):
            from app.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/session/end",
                    json=valid_request_body,
                    headers=auth_headers,
                )

            assert response.status_code == 500
            assert "Session end processing failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self, valid_request_body):
        """Request without auth headers returns HTTP 401."""
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/session/end",
                json=valid_request_body,
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, valid_request_body):
        """Request with wrong API key returns HTTP 401."""
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/session/end",
                json=valid_request_body,
                headers={"X-User-Id": "user-1", "X-Api-Key": "wrong-key"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_topic_returns_422(self, auth_headers):
        """Request missing required 'topic' field returns HTTP 422."""
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/session/end",
                json={"messages": [{"role": "user", "content": "hello"}]},
                headers=auth_headers,
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_messages_returns_422(self, auth_headers):
        """Request missing required 'messages' field returns HTTP 422."""
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/session/end",
                json={"topic": "python-basics"},
                headers=auth_headers,
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_message_role_returns_422(self, auth_headers):
        """Message with invalid role returns HTTP 422."""
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/session/end",
                json={
                    "topic": "python-basics",
                    "messages": [{"role": "system", "content": "hi"}],
                },
                headers=auth_headers,
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_skill_update_still_succeeds(
        self, auth_headers, valid_request_body
    ):
        """Session end with empty skill_update returns successfully."""
        result = {
            "session_id": "xyz-789",
            "title": "Quick Chat",
            "summary": "Brief discussion.",
            "skill_update": {},
        }
        with patch(
            "app.routers.session_end.process_session_end",
            new_callable=AsyncMock,
            return_value=result,
        ):
            from app.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/session/end",
                    json=valid_request_body,
                    headers=auth_headers,
                )

            assert response.status_code == 200
            assert response.json()["skill_update"] == {}
