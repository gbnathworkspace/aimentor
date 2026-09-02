"""Admin user management endpoints.

Provides paginated user listing, user deactivation (with token revocation),
and user activation. All endpoints require admin privileges.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import require_admin
from app.auth.token_manager import TokenManager
from app.config.database import get_db, llm_traces_col

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin_id: str = Depends(require_admin),
):
    """Return paginated user list. Default 20, max 100 per page.

    Excludes hashed_password field from results. Sorted by created_at descending.
    """
    db = get_db()
    skip = (page - 1) * page_size
    cursor = (
        db["users"]
        .find({}, {"_id": 0, "hashed_password": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    users = await cursor.to_list(page_size)
    total = await db["users"].count_documents({})
    return {"users": users, "total": total, "page": page, "page_size": page_size}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(user_id: str, admin_id: str = Depends(require_admin)):
    """Mark user inactive and revoke all their refresh tokens."""
    db = get_db()
    result = await db["users"].update_one(
        {"user_id": user_id}, {"$set": {"is_active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    # Revoke all refresh tokens for the deactivated user
    token_mgr = TokenManager()
    await token_mgr.revoke_all_user_tokens(user_id)
    return {"detail": "User deactivated"}


@router.post("/users/{user_id}/activate")
async def activate_user(user_id: str, admin_id: str = Depends(require_admin)):
    """Mark user active, allowing future authentication."""
    db = get_db()
    result = await db["users"].update_one(
        {"user_id": user_id}, {"$set": {"is_active": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"detail": "User activated"}


@router.get("/traces")
async def list_traces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin_id: str = Depends(require_admin),
):
    """Return paginated LLM call traces (see app/services/llm_trace.py), newest
    first. Traces auto-expire after 14 days (TTL index on created_at) — this
    is a debugging aid, not a permanent audit log.
    """
    col = llm_traces_col()
    skip = (page - 1) * page_size
    cursor = (
        col.find({}, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(page_size)
    )
    traces = await cursor.to_list(page_size)
    total = await col.count_documents({})
    return {"traces": traces, "total": total, "page": page, "page_size": page_size}
