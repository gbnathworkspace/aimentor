"""Unit tests for app.auth.token_manager.TokenManager."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _setup_settings():
    """Ensure settings are available with a known JWT_SECRET."""
    get_settings.cache_clear()
    env = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "DATABASE_NAME": "mentorman_test",
        "JWT_SECRET": "test-jwt-secret-key",
        "MENTORMAN_API_KEY": "test-api-key",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "VOYAGE_API_KEY": "voy-test",
    }
    with patch.dict(os.environ, env, clear=True):
        get_settings.cache_clear()
        get_settings()
        yield
    get_settings.cache_clear()


@pytest.fixture
def token_manager():
    from app.auth.token_manager import TokenManager

    return TokenManager()


class TestCreateAccessToken:
    """Tests for create_access_token()."""

    def test_returns_valid_jwt(self, token_manager):
        """Access token is a decodable JWT."""
        token = token_manager.create_access_token("user-123")
        claims = jwt.decode(token, "test-jwt-secret-key", algorithms=["HS256"])
        assert claims["sub"] == "user-123"

    def test_contains_required_claims(self, token_manager):
        """JWT contains sub, iat, and exp claims."""
        token = token_manager.create_access_token("user-456")
        claims = jwt.decode(
            token, "test-jwt-secret-key", algorithms=["HS256"]
        )
        assert "sub" in claims
        assert "iat" in claims
        assert "exp" in claims

    def test_expiry_is_15_minutes(self, token_manager):
        """Access token expires in 15 minutes."""
        token = token_manager.create_access_token("user-789")
        claims = jwt.decode(
            token, "test-jwt-secret-key", algorithms=["HS256"]
        )
        exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(claims["iat"], tz=timezone.utc)
        delta = exp - iat
        assert delta == timedelta(minutes=15)


class TestVerifyAccessToken:
    """Tests for verify_access_token()."""

    def test_valid_token_returns_user_id(self, token_manager):
        """Round-trip: create then verify returns same user_id."""
        token = token_manager.create_access_token("user-abc")
        result = token_manager.verify_access_token(token)
        assert result == "user-abc"

    def test_expired_token_raises(self, token_manager):
        """Expired token raises PyJWTError."""
        payload = {
            "sub": "user-expired",
            "iat": datetime.now(timezone.utc) - timedelta(hours=1),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=30),
        }
        token = jwt.encode(payload, "test-jwt-secret-key", algorithm="HS256")
        with pytest.raises(jwt.PyJWTError):
            token_manager.verify_access_token(token)

    def test_wrong_secret_raises(self, token_manager):
        """Token signed with wrong key fails verification."""
        payload = {
            "sub": "user-wrong-key",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(jwt.PyJWTError):
            token_manager.verify_access_token(token)

    def test_missing_sub_claim_raises(self, token_manager):
        """Token without sub claim fails verification."""
        payload = {
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, "test-jwt-secret-key", algorithm="HS256")
        with pytest.raises(jwt.PyJWTError):
            token_manager.verify_access_token(token)


class TestCreateRefreshToken:
    """Tests for create_refresh_token()."""

    @pytest.mark.asyncio
    async def test_returns_opaque_string(self, token_manager):
        """Refresh token is a non-empty string."""
        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            token_value = await token_manager.create_refresh_token("user-123")

        assert isinstance(token_value, str)
        assert len(token_value) > 0

    @pytest.mark.asyncio
    async def test_stores_document_in_mongodb(self, token_manager):
        """Refresh token doc is inserted into refresh_tokens collection."""
        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            token_value = await token_manager.create_refresh_token("user-456")

        mock_col.insert_one.assert_awaited_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["token"] == token_value
        assert doc["user_id"] == "user-456"
        assert doc["is_used"] is False
        assert "expires_at" in doc
        assert "created_at" in doc

    @pytest.mark.asyncio
    async def test_expiry_is_7_days(self, token_manager):
        """Refresh token document has a 7-day expiry."""
        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            await token_manager.create_refresh_token("user-789")

        doc = mock_col.insert_one.call_args[0][0]
        delta = doc["expires_at"] - doc["created_at"]
        # Allow small timing variance from two datetime.now() calls
        assert timedelta(days=7) <= delta < timedelta(days=7, seconds=1)


class TestRotateRefreshToken:
    """Tests for rotate_refresh_token()."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_new_pair(self, token_manager):
        """Valid, unused, unexpired token returns new access+refresh tokens."""
        now = datetime.now(timezone.utc)
        token_doc = {
            "_id": "obj-id-123",
            "token": "old-token-value",
            "user_id": "user-rotate",
            "created_at": now - timedelta(hours=1),
            "expires_at": now + timedelta(days=6),
            "is_used": False,
        }
        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=token_doc)
        mock_col.update_one = AsyncMock()
        mock_col.insert_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            access, refresh, user_id = await token_manager.rotate_refresh_token("old-token-value")

        assert user_id == "user-rotate"
        assert isinstance(access, str)
        assert isinstance(refresh, str)
        # Old token should be marked as used
        mock_col.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises_401(self, token_manager):
        """Token not in DB raises 401."""
        from fastapi import HTTPException

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=None)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            with pytest.raises(HTTPException) as exc:
                await token_manager.rotate_refresh_token("nonexistent")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, token_manager):
        """Expired token raises 401."""
        from fastapi import HTTPException

        now = datetime.now(timezone.utc)
        token_doc = {
            "_id": "obj-id-expired",
            "token": "expired-token",
            "user_id": "user-exp",
            "created_at": now - timedelta(days=8),
            "expires_at": now - timedelta(days=1),
            "is_used": False,
        }
        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=token_doc)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            with pytest.raises(HTTPException) as exc:
                await token_manager.rotate_refresh_token("expired-token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reused_token_revokes_all_and_raises_401(self, token_manager):
        """Reused token (is_used=True) revokes all user tokens and raises 401."""
        from fastapi import HTTPException

        now = datetime.now(timezone.utc)
        token_doc = {
            "_id": "obj-id-reused",
            "token": "reused-token",
            "user_id": "user-victim",
            "created_at": now - timedelta(hours=1),
            "expires_at": now + timedelta(days=6),
            "is_used": True,
        }
        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=token_doc)
        mock_col.delete_many = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            with pytest.raises(HTTPException) as exc:
                await token_manager.rotate_refresh_token("reused-token")

        assert exc.value.status_code == 401
        assert "reuse" in exc.value.detail.lower()
        # All user tokens should be revoked
        mock_col.delete_many.assert_awaited_once_with({"user_id": "user-victim"})


class TestRevokeRefreshToken:
    """Tests for revoke_refresh_token()."""

    @pytest.mark.asyncio
    async def test_deletes_token_document(self, token_manager):
        """Revoke deletes the token from the collection."""
        mock_col = MagicMock()
        mock_col.delete_one = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            await token_manager.revoke_refresh_token("some-token")

        mock_col.delete_one.assert_awaited_once_with({"token": "some-token"})


class TestRevokeAllUserTokens:
    """Tests for revoke_all_user_tokens()."""

    @pytest.mark.asyncio
    async def test_deletes_all_user_tokens(self, token_manager):
        """Revoke all deletes every token for the user."""
        mock_col = MagicMock()
        mock_col.delete_many = AsyncMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with patch("app.auth.token_manager.get_db", return_value=mock_db):
            await token_manager.revoke_all_user_tokens("user-to-revoke")

        mock_col.delete_many.assert_awaited_once_with({"user_id": "user-to-revoke"})
