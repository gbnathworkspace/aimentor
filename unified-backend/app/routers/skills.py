"""Skills router — /api/skills CRUD."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.config.database import skill_graph_col
from app.auth.dependencies import require_auth
from app.models.skill import SkillNode, SkillUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/skills", tags=["Skills"])


@router.get("", response_model=list[SkillNode])
async def list_skills(user_id: str = Depends(require_auth)) -> list[dict]:
    """Return all skill graph nodes for the authenticated user."""
    cursor = skill_graph_col().find({"user_id": user_id}, {"_id": 0, "user_id": 0})
    return await cursor.to_list(length=None)


@router.get("/{topic}", response_model=SkillNode)
async def get_skill(topic: str, user_id: str = Depends(require_auth)) -> dict:
    """Return a single skill node by topic. 404 if not found."""
    doc = await skill_graph_col().find_one(
        {"user_id": user_id, "topic": topic}, {"_id": 0, "user_id": 0}
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill topic '{topic}' not found",
        )
    return doc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SkillNode)
async def upsert_skill(data: SkillNode, user_id: str = Depends(require_auth)) -> dict:
    """Upsert a skill node. Creates if not exists, updates if it does."""
    doc = data.model_dump()
    try:
        await skill_graph_col().update_one(
            {"user_id": user_id, "topic": data.topic},
            {"$set": {**doc, "user_id": user_id}},
            upsert=True,
        )
    except Exception:
        logger.exception("Failed to upsert skill topic=%s for user=%s", data.topic, user_id)
        raise
    return doc


@router.put("/{topic}", response_model=SkillNode)
async def update_skill(
    topic: str, data: SkillUpdate, user_id: str = Depends(require_auth)
) -> dict:
    """Update a specific skill node. 404 if not found."""
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    result = await skill_graph_col().find_one_and_update(
        {"user_id": user_id, "topic": topic},
        {"$set": update_data},
        return_document=True,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill topic '{topic}' not found",
        )
    result.pop("_id", None)
    result.pop("user_id", None)
    return result


@router.delete("/{topic}")
async def delete_skill(topic: str, user_id: str = Depends(require_auth)) -> dict:
    """Remove a skill node by topic."""
    result = await skill_graph_col().delete_one({"user_id": user_id, "topic": topic})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill topic '{topic}' not found",
        )
    return {"ok": True}
