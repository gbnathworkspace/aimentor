"""Memory router — /api/memory/episodes search + list + delete."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config.database import sessions_col
from app.core.security import require_auth
from app.models.episodic import EpisodicEntry, SearchQuery
from app.services.embedder import embed_text

router = APIRouter(prefix="/api/memory/episodes", tags=["Memory"])


@router.post("/search")
async def search_episodes(
    body: SearchQuery,
    user_id: str = Depends(require_auth),
):
    """Perform vector search over episodic memory entries.

    Accepts a query string, optional topic filter, and limit.
    Returns matching episodes ranked by relevance score.
    """
    vector = await embed_text(body.query)

    if not vector:
        return []

    vector_filter = {"user_id": {"$eq": user_id}}
    if body.topic:
        vector_filter["topic"] = {"$eq": body.topic}

    pipeline = [
        {
            "$vectorSearch": {
                "index": "session_embedding_index",
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": max(20, body.limit * 10),
                "limit": body.limit,
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
                "topic_category": 1,
                "type": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    results = await sessions_col().aggregate(pipeline).to_list(body.limit)
    return results


@router.get("")
async def list_episodes(
    user_id: str = Depends(require_auth),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    topic: Optional[str] = Query(default=None),
):
    """Return paginated list of episodic memory entries for the user.

    Ordered by date descending. Supports optional topic filter.
    """
    query_filter: dict = {"user_id": user_id}
    if topic:
        query_filter["topic"] = topic

    cursor = (
        sessions_col()
        .find(query_filter, {"_id": 0, "embedding": 0})
        .sort("date", -1)
        .skip(offset)
        .limit(limit)
    )

    episodes = await cursor.to_list(limit)
    return episodes


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def delete_episode(
    session_id: str,
    user_id: str = Depends(require_auth),
):
    """Delete an episodic memory entry by session_id.

    Checks ownership — returns 404 if not found, 403 if not owned by user.
    """
    doc = await sessions_col().find_one({"session_id": session_id})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    if doc.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    await sessions_col().delete_one({"session_id": session_id})
    return {"ok": True}
