"""Authentication and authorization.

Primary path: networkless verification of Clerk session JWTs sent as
``Authorization: Bearer <token>``. The JWKS is fetched once and cached, so
steady-state verification makes no network call to Clerk.

Transition path: the legacy ``X-Api-Key`` / ``X-User-Id`` service-to-service
headers remain valid while ``LEGACY_AUTH_ENABLED`` is true.
"""

from functools import lru_cache

import jwt
from fastapi import Header, HTTPException, status

from app.config.settings import get_settings

_UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED


@lru_cache
def _jwk_client() -> "jwt.PyJWKClient":
    """Return a cached PyJWKClient for the configured Clerk JWKS URL.

    PyJWKClient caches signing keys after the first fetch, so verification is
    networkless in steady state.
    """
    settings = get_settings()
    url = settings.clerk_jwks_url
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clerk JWKS URL not configured",
        )
    return jwt.PyJWKClient(url, cache_keys=True)


def _get_signing_key(token: str):
    """Resolve the signing key for a token from the (cached) JWKS.

    Isolated as a seam so tests can patch key resolution and stay networkless.
    """
    return _jwk_client().get_signing_key_from_jwt(token).key


def verify_clerk_jwt(token: str) -> str:
    """Verify a Clerk session JWT and return its subject (user_id).

    Raises HTTP 401 on any verification failure.
    """
    settings = get_settings()
    decode_kwargs = {
        "algorithms": ["RS256"],
        # Clerk session tokens carry no `aud` by default; verify iss + signature + exp.
        "options": {"verify_aud": False, "require": ["exp", "iat", "sub"]},
    }
    if settings.CLERK_ISSUER:
        decode_kwargs["issuer"] = settings.CLERK_ISSUER

    try:
        signing_key = _get_signing_key(token)
        claims = jwt.decode(token, signing_key, **decode_kwargs)
    except jwt.PyJWTError:
        raise HTTPException(status_code=_UNAUTHORIZED, detail="Invalid token")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=_UNAUTHORIZED, detail="Token missing subject")
    return sub


async def require_auth(
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    """Authenticate a request and return the authenticated user_id.

    Prefers a Clerk JWT in the Authorization header; falls back to the legacy
    service-to-service headers while enabled.
    """
    # 1. Primary: Clerk JWT bearer token.
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return verify_clerk_jwt(token)

    # 2. Transition: legacy service-to-service headers.
    settings = get_settings()
    if settings.LEGACY_AUTH_ENABLED:
        if not x_api_key or x_api_key != settings.MENTORMAN_API_KEY:
            raise HTTPException(status_code=_UNAUTHORIZED, detail="Invalid API key")
        if not x_user_id:
            raise HTTPException(status_code=_UNAUTHORIZED, detail="Missing user ID")
        return x_user_id

    raise HTTPException(
        status_code=_UNAUTHORIZED, detail="Missing bearer token"
    )
