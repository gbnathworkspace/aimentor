"""L1 + L2 + L3 context assembly for mentor chat.

Gathers the user's profile, skill node for the topic, and relevant
past session episodes via vector search. Implements graceful degradation:
- Profile missing → HTTP 400 (onboarding required)
- Skill fetch fails → empty dict
- Vector search fails → empty list (logged warning)
"""

import logging

from fastapi import HTTPException, status

from app.config.database import (
    embeddings_col,
    profiles_col,
    skill_graph_col,
    sessions_col,
)

logger = logging.getLogger(__name__)

# ponytail: dump-all (capped), no vector search — onboarding uploads are a few
# chunks (résumé, problem list) tied to one user. Add vector ranking + the #5
# Atlas index only if uploads grow large/many.
_MAX_DOCUMENT_CHUNKS = 12


async def assemble(user_id: str, topic: str, query: str) -> dict:
    """Gather L1 profile, L2 skill, and L3 episodes for the given user/topic.

    Args:
        user_id: The authenticated user's ID.
        topic: The current mentoring topic.
        query: The user's latest message (used for vector search).

    Returns:
        A dict with keys: profile, skill, episodes.

    Raises:
        HTTPException(400): If no profile exists for the user.
    """
    # L1 — Profile (required)
    profile = await profiles_col().find_one({"user_id": user_id}, {"_id": 0})
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile found. Please complete onboarding first.",
        )

    # L2 — Skill node (optional, degrade gracefully)
    try:
        skill = await skill_graph_col().find_one(
            {"user_id": user_id, "topic": topic}, {"_id": 0}
        )
    except Exception as e:
        logger.warning("Skill graph fetch failed for user=%s topic=%s: %s", user_id, topic, e)
        skill = None

    # L3 — Episodic memory: most-recent ended-session summaries (optional).
    # `query` is reserved for future vector ranking (#5); recency works today
    # without an Atlas vector index. Degrades to [] on failure.
    episodes = await _recent_episodes(user_id, topic, limit=3)

    # Uploaded documents (résumé / LeetCode etc. ingested at onboarding).
    # Without this read the ingest pipeline is orphaned — files embedded, never used (issue #4).
    documents = await _fetch_documents(user_id)

    return {
        "profile": profile,
        "skill": skill or {},
        "episodes": episodes,
        "documents": documents,
    }


async def _fetch_documents(user_id: str, limit: int = _MAX_DOCUMENT_CHUNKS) -> list:
    """Fetch the user's ingested file chunks. Empty list on any failure."""
    try:
        cursor = embeddings_col().find(
            {"user_id": user_id, "metadata.source": "ingestion"},
            {"_id": 0, "text": 1, "metadata.filename": 1},
        ).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        logger.warning("Document fetch failed for user=%s: %s. Returning no documents.", user_id, e)
        return []


async def _recent_episodes(user_id: str, topic: str | None, limit: int) -> list:
    """Fetch the user's most recent ended-session summaries.

    Recency-based L3: no vector search. This avoids both the missing Atlas index
    and the writer/reader collection mismatch (#5), and works offline. Same-topic
    sessions are preferred, then filled with other recent ones. [] on any failure.
    """
    try:
        cursor = (
            sessions_col()
            .find(
                {"user_id": user_id, "status": "ended", "summary": {"$nin": [None, ""]}},
                {
                    "_id": 0,
                    "session_id": 1,
                    "title": 1,
                    "summary": 1,
                    "topic": 1,
                    "date": 1,
                    "skill_update": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(limit * 4)  # over-fetch so the same-topic preference has options
        )
        docs = await cursor.to_list(length=limit * 4)

        if topic:
            same = [d for d in docs if d.get("topic") == topic]
            others = [d for d in docs if d.get("topic") != topic]
            docs = same + others

        return docs[:limit]

    except Exception as e:
        logger.warning(
            "Recent-episode fetch failed for user=%s: %s. Returning empty episodes.",
            user_id,
            e,
        )
        return []
