"""Shared Atlas Vector Search plumbing: index management, embed+upsert, and
semantic search over `embeddings_col`. Used by both retrieval corpora —
uploaded documents (metadata.source="ingestion") and topic SummaryBlocks
(metadata.source="summary_block").

Fixes the historical writer/reader mismatch (issue #5): every writer here
uses the same field name ("embedding") and the same collection, so one
index serves both corpora, filtered by metadata.source at query time.
"""

import logging

from app.config.database import embeddings_col
from app.services.embedder import embed_text

logger = logging.getLogger(__name__)

VECTOR_INDEX_NAME = "vector_index"
# voyage-4-lite's default embedding dimensionality (embedder.py pins
# model="voyage-4-lite") — same 1024 dims as the old voyage-3, so no
# index/dimension migration needed, just a model-name/free-tier swap.
EMBEDDING_DIMENSIONS = 1024


async def ensure_vector_index() -> None:
    """Create the Atlas Vector Search index if it doesn't already exist.

    Idempotent — safe to call on every app startup. Filter fields let
    $vectorSearch pre-filter by user/source/topic instead of scanning then
    discarding, which matters once this collection holds many users' data.
    """
    try:
        existing = await embeddings_col().list_search_indexes().to_list(length=None)
        if any(idx.get("name") == VECTOR_INDEX_NAME for idx in existing):
            return

        await embeddings_col().create_search_index({
            "name": VECTOR_INDEX_NAME,
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": EMBEDDING_DIMENSIONS,
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "user_id"},
                    {"type": "filter", "path": "metadata.source"},
                    {"type": "filter", "path": "metadata.topic_id"},
                ]
            },
        })
        logger.info("Created Atlas Vector Search index %r on embeddings", VECTOR_INDEX_NAME)
    except Exception as e:
        # Fail-open at startup: retrieval degrades to empty results (see
        # vector_search()) rather than blocking app boot on an Atlas-side
        # issue (tier doesn't support it, transient API error, etc).
        logger.warning("Could not ensure vector index %r: %s", VECTOR_INDEX_NAME, e)


async def embed_and_upsert(
    vector_id: str, text: str, user_id: str, source: str, metadata: dict | None = None
) -> bool:
    """Embed `text` and upsert it, keyed by `vector_id` (idempotent).

    Returns False (and writes nothing) if the embedding call fails — an
    empty vector is worse than a missing one, it would silently poison
    every future similarity search against it.
    """
    vector = await embed_text(text)
    if not vector:
        logger.warning("Skipping upsert for vector_id=%s — embedding failed", vector_id)
        return False

    await embeddings_col().update_one(
        {"vector_id": vector_id},
        {
            "$set": {
                "vector_id": vector_id,
                "user_id": user_id,
                "text": text,
                "embedding": vector,
                "metadata": {"source": source, **(metadata or {})},
            }
        },
        upsert=True,
    )
    return True


async def delete_vectors(vector_ids: list[str]) -> None:
    """Remove embeddings by vector_id — used when source content (e.g. a
    merged-away SummaryBlock) no longer exists."""
    if not vector_ids:
        return
    await embeddings_col().delete_many({"vector_id": {"$in": vector_ids}})


async def list_topic_documents(topic_id: str, user_id: str) -> list[dict]:
    """List documents uploaded as context for one topic, one row per filename
    (a document is stored as many chunks — this collapses them back)."""
    pipeline = [
        {"$match": {"user_id": user_id, "metadata.topic_id": topic_id, "metadata.source": "topic_document"}},
        {"$group": {
            "_id": "$metadata.filename",
            "chunkCount": {"$sum": 1},
            "uploadedAt": {"$min": "$metadata.uploaded_at"},
        }},
        {"$project": {"_id": 0, "filename": "$_id", "chunkCount": 1, "uploadedAt": 1}},
        {"$sort": {"uploadedAt": -1}},
    ]
    return await embeddings_col().aggregate(pipeline).to_list(length=100)


async def delete_topic_document(topic_id: str, user_id: str, filename: str) -> int:
    """Delete every chunk of one topic-scoped document. Returns the number
    of chunks removed (0 means no such document)."""
    result = await embeddings_col().delete_many({
        "user_id": user_id, "metadata.topic_id": topic_id,
        "metadata.source": "topic_document", "metadata.filename": filename,
    })
    return result.deleted_count


async def vector_search(
    query: str, user_id: str, source: str, limit: int = 5, topic_id: str | None = None
) -> list[dict]:
    """Semantic search over embeddings_col, filtered to this user and source
    (and optionally one topic). Returns [] on any failure — retrieval is
    always a best-effort enhancement, never a hard dependency for a turn.
    """
    query_vector = await embed_text(query)
    if not query_vector:
        return []

    filter_clause: dict = {"user_id": user_id, "metadata.source": source}
    if topic_id is not None:
        filter_clause["metadata.topic_id"] = topic_id

    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(50, limit * 10),
                "limit": limit,
                "filter": filter_clause,
            }
        },
        {
            "$project": {
                "_id": 0,
                "text": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    try:
        return await embeddings_col().aggregate(pipeline).to_list(length=limit)
    except Exception as e:
        logger.warning("Vector search failed for user=%s source=%s: %s", user_id, source, e)
        return []
