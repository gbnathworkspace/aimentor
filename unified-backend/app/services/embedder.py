"""Voyage AI embedding service.

Provides async text embedding via the Voyage AI API.
Handles API failures gracefully — returns an empty list on error
so callers (e.g. session_end) can proceed with partial results.
"""

import logging
from typing import List

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
