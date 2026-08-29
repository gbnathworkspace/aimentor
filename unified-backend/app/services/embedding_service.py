"""EmbeddingService: async vector storage for session narrative summaries.

Generates vector embeddings via Voyage AI and upserts to the MongoDB
embeddings collection (Atlas Vector Search) with session metadata.
Runs asynchronously as fire-and-forget from the session-end pipeline.

Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s, max 8s).
On total failure: logs error and enqueues for delayed retry (5 min).
"""

import asyncio
import logging
from typing import Optional

import voyageai

from app.config.database import embeddings_col
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1  # seconds
_BACKOFF_CAP = 8  # seconds
_DELAYED_RETRY_SECONDS = 300  # 5 minutes

# Minimum summary length for embedding
_MIN_SUMMARY_LENGTH = 10


def _calculate_backoff(attempt: int) -> float:
    """Calculate exponential backoff delay: min(2^attempt * base, cap).

    Args:
        attempt: Zero-indexed retry attempt number.

    Returns:
        Delay in seconds before the next retry.
    """
    delay = (2**attempt) * _BACKOFF_BASE
    return min(delay, _BACKOFF_CAP)


async def embed_and_store(
    summary: str,
    user_id: str,
    session_id: str,
    topic: str,
    mode: str,
    ended_at: str,
) -> None:
    """Generate embedding via Voyage AI and upsert to Vector DB with metadata.

    Preconditions (skip with warning if not met):
      - summary must be non-empty and ≥10 characters
      - All metadata fields (user_id, session_id, topic, mode, ended_at)
        must be non-None and non-empty

    Uses session_id as the document identifier to ensure idempotency
    (upsert overwrites existing entry for same session_id).

    Args:
        summary: The narrative summary text to embed.
        user_id: The owning user's ID.
        session_id: The session being embedded.
        topic: Session topic.
        mode: Session mode (topic, planning, doubt, evaluation).
        ended_at: ISO-8601 UTC timestamp when session ended.
    """
    # Precondition: check summary length
    if not summary or len(summary.strip()) < _MIN_SUMMARY_LENGTH:
        logger.warning(
            "Skipping embedding — summary too short (length=%d) for session_id=%s",
            len(summary) if summary else 0,
            session_id,
        )
        return

    # Precondition: check required metadata fields
    metadata_fields = {
        "user_id": user_id,
        "session_id": session_id,
        "topic": topic,
        "mode": mode,
        "ended_at": ended_at,
    }
    missing_fields = [
        name for name, value in metadata_fields.items() if not value
    ]
    if missing_fields:
        logger.warning(
            "Skipping embedding — missing metadata fields %s for session_id=%s",
            missing_fields,
            session_id,
        )
        return

    # Attempt embedding + storage with retries
    try:
        await _embed_and_store_with_retry(
            summary=summary,
            user_id=user_id,
            session_id=session_id,
            topic=topic,
            mode=mode,
            ended_at=ended_at,
        )
    except _EmbeddingFailedError as e:
        logger.error(
            "Embedding failed after %d attempts for session_id=%s: %s. "
            "Scheduling delayed retry in %d seconds.",
            _MAX_ATTEMPTS,
            session_id,
            str(e),
            _DELAYED_RETRY_SECONDS,
        )
        # Enqueue delayed retry (fire-and-forget)
        asyncio.create_task(
            _delayed_retry(
                summary=summary,
                user_id=user_id,
                session_id=session_id,
                topic=topic,
                mode=mode,
                ended_at=ended_at,
            )
        )


class _EmbeddingFailedError(Exception):
    """Internal error raised when all retry attempts are exhausted."""

    pass


async def _embed_and_store_with_retry(
    summary: str,
    user_id: str,
    session_id: str,
    topic: str,
    mode: str,
    ended_at: str,
) -> None:
    """Generate embedding and upsert with retry logic.

    Retries up to _MAX_ATTEMPTS with exponential backoff.

    Raises:
        _EmbeddingFailedError: If all attempts fail.
    """
    last_error: Optional[Exception] = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            # Generate embedding via Voyage AI
            vector = await _generate_embedding(summary)
            if not vector:
                raise _EmbeddingFailedError(
                    "Voyage AI returned empty embedding"
                )

            # Upsert to Vector DB (MongoDB Atlas Vector Search)
            await _upsert_vector(
                vector=vector,
                summary=summary,
                user_id=user_id,
                session_id=session_id,
                topic=topic,
                mode=mode,
                ended_at=ended_at,
            )
            logger.info(
                "Successfully embedded and stored summary for session_id=%s",
                session_id,
            )
            return

        except _EmbeddingFailedError:
            raise
        except Exception as e:
            last_error = e
            logger.warning(
                "Embedding attempt %d/%d failed for session_id=%s: %s",
                attempt + 1,
                _MAX_ATTEMPTS,
                session_id,
                str(e),
            )
            # Don't sleep after the last attempt
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _calculate_backoff(attempt)
                await asyncio.sleep(delay)

    raise _EmbeddingFailedError(
        f"All {_MAX_ATTEMPTS} attempts failed: {last_error}"
    )


async def _generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for text via Voyage AI async client.

    Args:
        text: The text to embed.

    Returns:
        List of floats representing the embedding vector.

    Raises:
        Exception: If the Voyage AI API call fails.
    """
    settings = get_settings()
    client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
    response = await client.embed(texts=[text], model="voyage-4-lite")
    return response.embeddings[0]


async def _upsert_vector(
    vector: list[float],
    summary: str,
    user_id: str,
    session_id: str,
    topic: str,
    mode: str,
    ended_at: str,
) -> None:
    """Upsert embedding vector to MongoDB Atlas Vector Search.

    Uses session_id as the unique identifier to prevent duplicates.
    Overwrites existing entry for the same session_id.

    Args:
        vector: The embedding vector.
        summary: The original summary text.
        user_id: The user's ID.
        session_id: The session identifier (used as upsert key).
        topic: Session topic.
        mode: Session mode.
        ended_at: Session end timestamp.
    """
    document = {
        "vector": vector,
        "text": summary,
        "metadata": {
            "user_id": user_id,
            "session_id": session_id,
            "topic": topic,
            "mode": mode,
            "ended_at": ended_at,
        },
    }

    await embeddings_col().update_one(
        {"metadata.session_id": session_id},
        {"$set": document},
        upsert=True,
    )


async def _delayed_retry(
    summary: str,
    user_id: str,
    session_id: str,
    topic: str,
    mode: str,
    ended_at: str,
) -> None:
    """Delayed retry after initial failure. Waits 5 minutes then retries once.

    This is a last-resort background task. If it fails again, the error
    is logged and no further automatic retry occurs.
    """
    await asyncio.sleep(_DELAYED_RETRY_SECONDS)

    logger.info(
        "Executing delayed embedding retry for session_id=%s",
        session_id,
    )

    try:
        await _embed_and_store_with_retry(
            summary=summary,
            user_id=user_id,
            session_id=session_id,
            topic=topic,
            mode=mode,
            ended_at=ended_at,
        )
    except _EmbeddingFailedError as e:
        logger.error(
            "Delayed embedding retry also failed for session_id=%s: %s. "
            "Manual intervention may be required.",
            session_id,
            str(e),
        )
    except Exception as e:
        logger.error(
            "Unexpected error during delayed embedding retry for session_id=%s: %s",
            session_id,
            str(e),
        )
