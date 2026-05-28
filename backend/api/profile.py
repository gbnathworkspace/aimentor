from fastapi import APIRouter
from core.models import CoreProfile
from memory.layer1 import get_profile, upsert_profile
from memory.layer2 import get_skill_graph

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{user_id}")
async def fetch_profile(user_id: str):
    profile = await get_profile(user_id)
    skill_graph = await get_skill_graph(user_id)
    return {"profile": profile, "skill_graph": skill_graph}


@router.post("/")
async def save_profile(profile: CoreProfile):
    await upsert_profile(profile)
    return {"status": "ok"}
