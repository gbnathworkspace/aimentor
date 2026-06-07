from fastapi import APIRouter, Depends, status

from app.core.security import verify_api_key
from app.models.l1 import CoreProfile, ProfileUpdate
from app.memory.l1 import crud

router = APIRouter(
    prefix="/memory/profile",
    tags=["L1 Profile"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/{user_id}")
def get_profile(user_id: str):
    return crud.get_profile(user_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(data: CoreProfile):
    return crud.create_profile(data)


@router.put("/{user_id}")
def update_profile(user_id: str, data: ProfileUpdate):
    return crud.update_profile(user_id, data)


@router.delete("/{user_id}")
def delete_profile(user_id: str):
    return crud.delete_profile(user_id)
