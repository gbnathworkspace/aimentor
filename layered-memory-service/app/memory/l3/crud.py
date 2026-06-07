from datetime import datetime, timezone
from uuid import uuid4

from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException, status

from app.dal.mongo import get_sessions_collection
from app.models.l3 import EpisodicEntry, SearchQuery
from app.memory.l3 import embeddings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def list_sessions(user_id: str, limit: int, offset: int, topic: str | None) -> dict:
    query: dict = {"user_id": user_id}
    if topic:
        query["topic"] = topic

    col = get_sessions_collection()
    total = col.count_documents(query)
    cursor = (
        col.find(query, {"_id": 0, "embedding": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    return {"total": total, "limit": limit, "offset": offset, "results": list(cursor)}


async def save_session(user_id: str, data: EpisodicEntry) -> dict:
    session_id = str(uuid4())
    vector = await embeddings.embed(data.summary)
    doc = data.model_dump()
    doc["user_id"] = user_id
    doc["session_id"] = session_id
    doc["embedding"] = vector
    doc["created_at"] = _now()
    try:
        get_sessions_collection().insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already exists")
    return {"session_id": session_id, "created": True}


async def search_sessions(user_id: str, query: SearchQuery) -> list[dict]:
    vector = await embeddings.embed(query.query)
    limit = max(1, query.limit)
    num_candidates = max(20, limit * 10)

    vector_filter: dict = {"user_id": {"$eq": user_id}}
    if query.topic:
        vector_filter["topic"] = {"$eq": query.topic}

    pipeline = [
        {
            "$vectorSearch": {
                "index": "session_embedding_index",
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": num_candidates,
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

    results = list(get_sessions_collection().aggregate(pipeline))
    return results


def delete_session(user_id: str, session_id: str) -> dict:
    result = get_sessions_collection().delete_one({"user_id": user_id, "session_id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"session_id": session_id, "deleted": True}
