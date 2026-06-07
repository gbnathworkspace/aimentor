"""Unit tests for app/core/security.py — auth middleware validation."""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.config.settings import get_settings


class TestRequireAuth:
    """Verify require_auth dependency validates headers correctly."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        """Ensure get_settings returns a predictable API key for all tests."""
        get_settings.cache_clear()
        env = {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MENTORMAN_API_KEY": "test-api-key",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "VOYAGE_API_KEY": "voy-test",
        }
        with patch.dict(os.environ, env, clear=True):
            # Pre-warm the cache so require_auth picks up our test key
            get_settings()
            yield
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_valid_headers_return_user_id(self):
        """Valid X-Api-Key and X-User-Id returns the user_id string."""
        from app.core.security import require_auth

        result = await require_auth(
            x_user_id="user-abc-123",
            x_api_key="test-api-key",
        )
        assert result == "user-abc-123"

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_401(self):
        """Missing X-Api-Key header raises HTTP 401."""
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(x_user_id="user-abc-123", x_api_key=None)

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self):
        """Invalid X-Api-Key header raises HTTP 401."""
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(x_user_id="user-abc-123", x_api_key="wrong-key")

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_401(self):
        """Missing X-User-Id header raises HTTP 401."""
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(x_user_id=None, x_api_key="test-api-key")

        assert exc_info.value.status_code == 401
        assert "Missing user ID" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_both_missing_returns_401(self):
        """Both headers missing raises HTTP 401 (API key checked first)."""
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc_info:
            await require_auth(x_user_id=None, x_api_key=None)

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail
