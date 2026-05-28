from core.database import get_collection
from core.models import CoreProfile


async def get_profile(user_id: str) -> dict | None:
    col = get_collection("users")
    return await col.find_one({"user_id": user_id}, {"_id": 0})


async def upsert_profile(profile: CoreProfile) -> None:
    col = get_collection("users")
    await col.update_one(
        {"user_id": profile.user_id},
        {"$set": profile.model_dump()},
        upsert=True,
    )


def format_for_context(profile: dict) -> str:
    return (
        f"User goal: {profile.get('goal')}\n"
        f"Deadline: {profile.get('deadline')}\n"
        f"Current level: {profile.get('overall_level')}\n"
        f"Daily availability: {profile.get('daily_availability')}"
    )
