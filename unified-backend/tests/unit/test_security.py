"""Unit tests for app/core/security.py — auth middleware validation.

Covers two auth paths:
  * Bearer JWT (primary): HS256 verification of the Authorization Bearer token.
  * Legacy X-Api-Key / X-User-Id (kept behind LEGACY_AUTH_ENABLED during transition).
"""

import datetime
import os
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.config.settings import get_settings


class TestLegacyHeaderAuth:
    """Verify the legacy X-Api-Key / X-User-Id path still works during transition."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        get_settings.cache_clear()
        env = {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MENTORMAN_API_KEY": "test-api-key",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "VOYAGE_API_KEY": "voy-test",
            "LEGACY_AUTH_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            get_settings()
            yield
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_valid_headers_return_user_id(self):
        from app.core.security import require_auth

        result = await require_auth(
            authorization=None, x_user_id="user-abc-123", x_api_key="test-api-key"
        )
        assert result == "user-abc-123"

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self):
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=None, x_user_id="user-abc-123", x_api_key="wrong-key"
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_401(self):
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=None, x_user_id=None, x_api_key="test-api-key"
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_all_missing_returns_401(self):
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc:
            await require_auth(authorization=None, x_user_id=None, x_api_key=None)
        assert exc.value.status_code == 401


class TestBearerJWTAuth:
    """Verify HS256 Bearer JWT verification on the Authorization header."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        get_settings.cache_clear()
        env = {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MENTORMAN_API_KEY": "test-api-key",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "VOYAGE_API_KEY": "voy-test",
            "JWT_SECRET": "test-jwt-secret",
            "LEGACY_AUTH_ENABLED": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            get_settings()
            # Refresh the module-level TokenManager so it picks up the test secret
            with patch("app.auth.dependencies._token_manager.settings", get_settings()):
                yield
        get_settings.cache_clear()

    def _mint_hs256_token(self, sub: str = "user_999", expires_in: int = 3600) -> str:
        """Mint an HS256 JWT for tests."""
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": sub,
            "iat": now,
            "exp": now + datetime.timedelta(seconds=expires_in),
        }
        return jwt.encode(payload, "test-jwt-secret", algorithm="HS256")

    @pytest.mark.asyncio
    async def test_valid_jwt_returns_sub(self):
        from app.core.security import require_auth

        token = self._mint_hs256_token(sub="user_999")

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())
        mock_db["users"].find_one = AsyncMock(return_value=None)

        with patch("app.auth.dependencies.get_db", return_value=mock_db):
            result = await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert result == "user_999"

    @pytest.mark.asyncio
    async def test_bearer_is_case_insensitive(self):
        from app.core.security import require_auth

        token = self._mint_hs256_token(sub="user_abc")

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())
        mock_db["users"].find_one = AsyncMock(return_value=None)

        with patch("app.auth.dependencies.get_db", return_value=mock_db):
            result = await require_auth(
                authorization=f"bearer {token}", x_user_id=None, x_api_key=None
            )
        assert result == "user_abc"

    @pytest.mark.asyncio
    async def test_expired_jwt_returns_401(self):
        from app.core.security import require_auth

        token = self._mint_hs256_token(expires_in=-10)
        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self):
        """A token signed with a different secret fails verification."""
        from app.core.security import require_auth

        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "user_abc",
            "iat": now,
            "exp": now + datetime.timedelta(seconds=3600),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_garbage_token_returns_401(self):
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization="Bearer not-a-jwt", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_auth_with_legacy_disabled_returns_401(self):
        from app.core.security import require_auth

        with pytest.raises(HTTPException) as exc:
            await require_auth(authorization=None, x_user_id=None, x_api_key=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_without_sub_returns_401(self):
        from app.core.security import require_auth

        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "",
            "iat": now,
            "exp": now + datetime.timedelta(seconds=3600),
        }
        token = jwt.encode(payload, "test-jwt-secret", algorithm="HS256")

        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401
