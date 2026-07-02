"""FastAPI authentication dependencies.

Provides require_auth() and require_admin() dependencies that authenticate
requests using self-issued HS256 JWTs (primary) or legacy service-to-service
headers (transition path).

Priority: Bearer JWT > Legacy headers (X-Api-Key + X-User-Id).
If a Bearer token is present but invalid, we return 401 immediately (no fallback).
"""

from fastapi import Depends, Header, HTTPException, status

from app.auth.token_manager import TokenManager
from app.config.database import get_db
from app.config.settings import get_settings

_token_manager = TokenManager()


async def require_auth(
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    """Authenticate a request and return the authenticated user_id.

    Priority:
      1. Self-issued HS256 JWT in Authorization: Bearer <token>
      2. Legacy X-Api-Key + X-User-Id headers (while LEGACY_AUTH_ENABLED=true)

    If a Bearer token is present but invalid, raises 401 immediately without
    falling back to legacy headers.
    """
    # 1. Primary: Self-issued JWT bearer token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            user_id = _token_manager.verify_access_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject",
            )
        # Check user is active
        db = get_db()
        user = await db["users"].find_one({"user_id": user_id}, {"is_active": 1})
        if user and not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account deactivated",
            )
        return user_id

    # 2. Legacy: X-Api-Key + X-User-Id (while flag enabled)
    settings = get_settings()
    if settings.LEGACY_AUTH_ENABLED:
        if not x_api_key or x_api_key != settings.MENTORMAN_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        if not x_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing user ID",
            )
        return x_user_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing bearer token",
    )


async def require_admin(
    user_id: str = Depends(require_auth),
) -> str:
    """Verify the authenticated user has admin privileges.

    Depends on require_auth() to authenticate the user first, then checks
    the is_admin flag in the users collection.
    """
    db = get_db()
    user = await db["users"].find_one({"user_id": user_id}, {"is_admin": 1})
    if not user or not user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user_id
