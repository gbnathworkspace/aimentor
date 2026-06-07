from fastapi import APIRouter, Depends, Query, status

from app.core.security import verify_api_key
from app.models.l3 import EpisodicEntry, SearchQuery
from app.memory.l3 import crud

router = APIRouter(
    prefix="/memory/episodic",
    tags=["L3 Episodic"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/{user_id}")
def list_sessions(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    topic: str | None = Query(default=None),
):
    return crud.list_sessions(user_id, limit, offset, topic)


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def save_session(user_id: str, data: EpisodicEntry):
    return await crud.save_session(user_id, data)


@router.post("/{user_id}/search")
async def search_sessions(user_id: str, data: SearchQuery):
    return await crud.search_sessions(user_id, data)


@router.delete("/{user_id}/{session_id}")
def delete_session(user_id: str, session_id: str):
    return crud.delete_session(user_id, session_id)
