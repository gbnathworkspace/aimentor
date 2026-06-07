import logging
from fastapi import HTTPException
from app.memory.l1.crud import get_profile
from app.memory.l2.crud import get_skill
from app.memory.l3.crud import search_sessions
from app.models.l3 import SearchQuery

logger = logging.getLogger(__name__)


async def assemble(user_id: str, topic: str, query: str) -> dict:
    try:
        profile = get_profile(user_id)
    except HTTPException:
        profile = {}
    except Exception as e:
        logger.warning("L1 fetch failed: %s", e)
        profile = {}

    try:
        skill = get_skill(user_id, topic)
    except HTTPException:
        skill = {}
    except Exception as e:
        logger.warning("L2 fetch failed: %s", e)
        skill = {}

    try:
        episodes = await search_sessions(user_id, SearchQuery(query=query, limit=3, topic=topic))
    except Exception as e:
        logger.warning("L3 search failed: %s", e)
        episodes = []

    return {"profile": profile, "skill": skill, "episodes": episodes}
