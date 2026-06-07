"""Unit tests for app/core/security.py — auth middleware validation.

Covers two auth paths:
  * Clerk JWT (primary): networkless JWKS verification of the Authorization Bearer token.
  * Legacy X-Api-Key / X-User-Id (kept behind LEGACY_AUTH_ENABLED during transition).
"""

import datetime
import os
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.config.settings import get_settings

# ─── Test RSA keypair (module-level, generated once) ──────────────────────────
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_PUBLIC_PEM = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

_ISSUER = "https://test-app.clerk.accounts.dev"


def _mint_token(
    sub: str = "user_clerk_123",
    issuer: str = _ISSUER,
    expires_in: int = 3600,
    extra_claims: dict | None = None,
    key=_PRIVATE_PEM,
) -> str:
    """Mint a Clerk-style RS256 JWT for tests."""
    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {
        "sub": sub,
        "iss": issuer,
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(seconds=expires_in),
        "azp": "https://test-app",
        "sid": "sess_123",
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, key, algorithm="RS256")


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
            "CLERK_ISSUER": _ISSUER,
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


class TestClerkJWTAuth:
    """Verify networkless Clerk JWT verification on the Authorization header."""

    @pytest.fixture(autouse=True)
    def _setup_settings(self):
        get_settings.cache_clear()
        env = {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MENTORMAN_API_KEY": "test-api-key",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "VOYAGE_API_KEY": "voy-test",
            "CLERK_ISSUER": _ISSUER,
            "LEGACY_AUTH_ENABLED": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            get_settings()
            # Patch signing-key resolution so verification is networkless in tests.
            with patch(
                "app.core.security._get_signing_key", return_value=_PUBLIC_PEM
            ):
                yield
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_valid_jwt_returns_sub(self):
        from app.core.security import require_auth

        token = _mint_token(sub="user_clerk_999")
        result = await require_auth(
            authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
        )
        assert result == "user_clerk_999"

    @pytest.mark.asyncio
    async def test_bearer_is_case_insensitive(self):
        from app.core.security import require_auth

        token = _mint_token(sub="user_abc")
        result = await require_auth(
            authorization=f"bearer {token}", x_user_id=None, x_api_key=None
        )
        assert result == "user_abc"

    @pytest.mark.asyncio
    async def test_expired_jwt_returns_401(self):
        from app.core.security import require_auth

        token = _mint_token(expires_in=-10)  # already expired
        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_issuer_returns_401(self):
        from app.core.security import require_auth

        token = _mint_token(issuer="https://evil.example.com")
        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_signature_returns_401(self):
        """A token signed by a different key fails signature verification."""
        from app.core.security import require_auth

        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = _mint_token(key=other_pem)  # signed by a key the JWKS doesn't know
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

        # Mint a token then strip sub by minting with empty sub claim
        token = _mint_token(sub="", extra_claims={"sub": ""})
        with pytest.raises(HTTPException) as exc:
            await require_auth(
                authorization=f"Bearer {token}", x_user_id=None, x_api_key=None
            )
        assert exc.value.status_code == 401
