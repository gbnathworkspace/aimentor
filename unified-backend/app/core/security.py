"""Authentication and authorization via trusted headers."""

from fastapi import Header, HTTPException, status

from app.config.settings import get_settings


async def require_auth(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
) -> str:
    """Validate X-Api-Key and X-User-Id headers. Returns the authenticated user_id."""
    settings = get_settings()
    if not x_api_key or x_api_key != settings.MENTORMAN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing user ID"
        )
    return x_user_id
