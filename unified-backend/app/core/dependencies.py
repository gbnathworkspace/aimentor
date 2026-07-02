"""Common FastAPI dependencies."""

from fastapi import Depends

from app.auth.dependencies import require_auth


async def get_current_user(user_id: str = Depends(require_auth)) -> str:
    """Dependency that returns the current authenticated user ID."""
    return user_id
