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
from app.services.embedder import embed_text

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

    # L3 — Episodic memory via vector search (optional, degrade gracefully)
    episodes = await _vector_search(user_id, query, topic, limit=3)

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


async def _vector_search(
    user_id: str, query: str, topic: str | None, limit: int
) -> list:
    """Perform vector search on sessions collection for relevant episodes.

    Uses the shared embedder service instead of an inline Voyage client call.
    Returns an empty list on any failure so the mentor can still respond.
    """
    try:
        vector = await embed_text(query)
        if not vector:
            logger.warning("Embedding returned empty vector; skipping vector search.")
            return []

        vector_filter = {"user_id": {"$eq": user_id}}
        if topic:
            vector_filter["topic"] = {"$eq": topic}

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "session_embedding_index",
                    "path": "embedding",
                    "queryVector": vector,
                    "numCandidates": max(20, limit * 10),
                    "limit": limit,
                    "filter": vector_filter,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "embedding": 0,
                    "session_id": 1,
                    "title": 1,
                    "summary": 1,
                    "topic": 1,
                    "date": 1,
                    "skill_update": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        results = await sessions_col().aggregate(pipeline).to_list(limit)
        return results

    except Exception as e:
        logger.warning(
            "Vector search failed for user=%s query=%r: %s. Returning empty episodes.",
            user_id,
            query[:50],
            e,
        )
        return []
