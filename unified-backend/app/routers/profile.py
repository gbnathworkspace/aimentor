"""Profile router — /api/profile CRUD."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.config.database import profiles_col
from app.core.security import require_auth
from app.models.profile import ProfileCreate, ProfileResponse, ProfileUpdate

router = APIRouter(prefix="/api/profile", tags=["Profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(require_auth)):
    """Return the L1 profile for the authenticated user."""
    doc = await profiles_col().find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return doc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProfileResponse)
async def create_profile(
    data: ProfileCreate, user_id: str = Depends(require_auth)
):
    """Create a new profile for the authenticated user."""
    doc = data.model_dump()
    doc["user_id"] = user_id
    try:
        await profiles_col().insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists for this user",
        )
    doc.pop("_id", None)
    return doc


@router.put("", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdate, user_id: str = Depends(require_auth)
):
    """Update the profile for the authenticated user."""
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        # Nothing to update — just return existing profile
        doc = await profiles_col().find_one({"user_id": user_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Profile not found")
        return doc

    result = await profiles_col().find_one_and_update(
        {"user_id": user_id},
        {"$set": update_data},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Profile not found")
    result.pop("_id", None)
    return result


@router.delete("")
async def delete_profile(user_id: str = Depends(require_auth)):
    """Delete the profile for the authenticated user."""
    result = await profiles_col().delete_one({"user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"ok": True}
