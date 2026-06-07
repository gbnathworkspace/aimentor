from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException, status

from app.dal.mongo import get_profiles_collection
from app.models.l1 import CoreProfile, ProfileUpdate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def get_profile(user_id: str) -> dict:
    doc = get_profiles_collection().find_one({"user_id": user_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return _strip_id(doc)


def create_profile(data: CoreProfile) -> dict:
    doc = data.model_dump()
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    try:
        get_profiles_collection().insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile already exists")
    return {"user_id": data.user_id, "created": True}


def update_profile(user_id: str, data: ProfileUpdate) -> dict:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    updates["updated_at"] = _now()
    result = get_profiles_collection().update_one({"user_id": user_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return {"user_id": user_id, "updated": True}


def delete_profile(user_id: str) -> dict:
    result = get_profiles_collection().delete_one({"user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return {"user_id": user_id, "deleted": True}
