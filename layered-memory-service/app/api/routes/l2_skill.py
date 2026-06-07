from fastapi import APIRouter, Depends, status

from app.core.security import verify_api_key
from app.models.l2 import SkillNode, SkillUpdate
from app.memory.l2 import crud

router = APIRouter(
    prefix="/memory/skill",
    tags=["L2 Skill Graph"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/{user_id}")
def get_all_skills(user_id: str):
    return crud.get_all_skills(user_id)


@router.get("/{user_id}/{topic}")
def get_skill(user_id: str, topic: str):
    return crud.get_skill(user_id, topic)


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
def create_skill(user_id: str, data: SkillNode):
    return crud.create_skill(user_id, data)


@router.put("/{user_id}/{topic}")
def update_skill(user_id: str, topic: str, data: SkillUpdate):
    return crud.update_skill(user_id, topic, data)


@router.delete("/{user_id}/{topic}")
def delete_skill(user_id: str, topic: str):
    return crud.delete_skill(user_id, topic)
