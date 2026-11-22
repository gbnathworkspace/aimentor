"""Voyage AI embedding service.

Provides async text embedding via the Voyage AI API.
Handles API failures gracefully — returns an empty list on error
so callers (e.g. session_end) can proceed with partial results.
"""

import logging
from typing import List, Optional

import voyageai

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


async def embed_text(text: str) -> List[float]:
    """Embed a single text string using Voyage AI.

    Args:
        text: The text to embed.

    Returns:
        A list of floats representing the embedding vector.
        Returns an empty list if the API call fails.
    """
    if not text or not text.strip():
        logger.warning("embed_text called with empty text, returning empty embedding")
        return []

    settings = get_settings()

    try:
        client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
        response = await client.embed(texts=[text], model="voyage-4-lite")
        return response.embeddings[0]
    except Exception as e:
        logger.warning(
            "Voyage AI embedding failed: %s. Returning empty embedding.",
            str(e),
        )
        return []


# Voyage allows up to 1000 texts per call; 64 keeps each request small
# while turning a long transcript into a handful of calls, not hundreds
# (the free tier is rate-limited per request).
_BATCH_SIZE = 64


async def embed_texts(texts: List[str], input_type: Optional[str] = None) -> List[List[float]]:
    """Embed many texts in batched Voyage calls, same model as embed_text.

    Unlike embed_text this raises on failure: a bulk job (video ingest)
    must report "failed" with the reason, not quietly store nothing.

    Returns one vector per input text, in order.
    """
    settings = get_settings()
    client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
    vectors: List[List[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i:i + _BATCH_SIZE]
        response = await client.embed(texts=batch, model="voyage-4-lite", input_type=input_type)
        vectors.extend(response.embeddings)
    return vectors
