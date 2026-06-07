from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException, status

from app.dal.mongo import get_skill_graph_collection
from app.models.l2 import SkillNode, SkillUpdate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def get_all_skills(user_id: str) -> list[dict]:
    cursor = get_skill_graph_collection().find({"user_id": user_id}, {"_id": 0})
    return list(cursor)


def get_skill(user_id: str, topic: str) -> dict:
    doc = get_skill_graph_collection().find_one({"user_id": user_id, "topic": topic})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill node not found")
    return _strip_id(doc)


def create_skill(user_id: str, data: SkillNode) -> dict:
    doc = data.model_dump()
    doc["user_id"] = user_id
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    try:
        get_skill_graph_collection().insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill node already exists")
    return {"user_id": user_id, "topic": data.topic, "created": True}


def update_skill(user_id: str, topic: str, data: SkillUpdate) -> dict:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    updates["updated_at"] = _now()
    result = get_skill_graph_collection().update_one(
        {"user_id": user_id, "topic": topic}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill node not found")
    return {"user_id": user_id, "topic": topic, "updated": True}


def upsert_skill(user_id: str, topic: str, data: SkillUpdate) -> dict:
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    updates["updated_at"] = _now()
    get_skill_graph_collection().update_one(
        {"user_id": user_id, "topic": topic},
        {"$set": updates},
        upsert=True,
    )
    return {"user_id": user_id, "topic": topic, "upserted": True}


def delete_skill(user_id: str, topic: str) -> dict:
    result = get_skill_graph_collection().delete_one({"user_id": user_id, "topic": topic})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill node not found")
    return {"user_id": user_id, "topic": topic, "deleted": True}
