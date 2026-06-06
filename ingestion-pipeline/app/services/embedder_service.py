"""EmbedderService: generates vector embeddings via Voyage AI and stores in Atlas Vector Search."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voyageai

from app.config.database import get_embeddings_collection
from app.config.settings import get_settings
from app.models.schemas import Chunk

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding or storage permanently fails after all retries."""

    pass


class EmbedderService:
    """Generate vector embeddings and store in Atlas Vector Search.

    Processes chunks in batches of 20, calls Voyage AI for embeddings,
    and persists results to the MongoDB embeddings collection.
    """

    BATCH_SIZE = 20
    MAX_API_RETRIES = 3
    MAX_STORAGE_RETRIES = 2
    BACKOFF_BASE = 1  # seconds
    BACKOFF_CAP = 8  # seconds

    def __init__(self) -> None:
        settings = get_settings()
        self._client = voyageai.Client(api_key=settings.VOYAGE_AI_API_KEY)

    async def embed_and_store(self, chunks: list[Chunk]) -> None:
        """Embed all chunks and store them in Atlas Vector Search.

        Splits chunks into batches of BATCH_SIZE and processes each
        batch sequentially: first generating embeddings via Voyage AI,
        then storing the results in the embeddings collection.

        Args:
            chunks: List of Chunk objects to embed and store.

        Raises:
            EmbeddingError: If embedding or storage fails after all retries.
        """
        if not chunks:
            return

        batches = self._batch_chunks(chunks)

        for batch in batches:
            # Generate embeddings for this batch
            texts = [chunk.text for chunk in batch]
            embeddings = await self._embed_with_retry(texts)

            # Build documents for storage
            documents = []
            for chunk, vector in zip(batch, embeddings):
                documents.append(
                    {
                        "vector": vector,
                        "text": chunk.text,
                        "metadata": chunk.metadata.model_dump(),
                    }
                )

            # Store in Atlas Vector Search
            await self._store_with_retry(documents)

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Call Voyage AI with retry logic and exponential backoff.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).

        Raises:
            EmbeddingError: If all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_API_RETRIES):
            try:
                result = self._client.embed(texts, model="voyage-3-lite")
                return result.embeddings
            except Exception as e:
                last_error = e
                logger.warning(
                    "Voyage AI embedding attempt %d/%d failed: %s",
                    attempt + 1,
                    self.MAX_API_RETRIES,
                    str(e),
                )

                # Don't sleep after the last attempt
                if attempt < self.MAX_API_RETRIES - 1:
                    delay = self._calculate_backoff(attempt)
                    await asyncio.sleep(delay)

        raise EmbeddingError(
            f"Voyage AI embedding failed after {self.MAX_API_RETRIES} retries: {last_error}"
        )

    async def _store_with_retry(self, documents: list[dict[str, Any]]) -> None:
        """Store documents in the embeddings collection with retry logic.

        Uses a fixed 1-second delay between retries.

        Args:
            documents: List of documents to insert into the embeddings collection.

        Raises:
            EmbeddingError: If all storage retries are exhausted.
        """
        last_error: Exception | None = None
        collection = get_embeddings_collection()

        for attempt in range(self.MAX_STORAGE_RETRIES):
            try:
                await collection.insert_many(documents)
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "Atlas Vector Search storage attempt %d/%d failed: %s",
                    attempt + 1,
                    self.MAX_STORAGE_RETRIES,
                    str(e),
                )

                # Don't sleep after the last attempt
                if attempt < self.MAX_STORAGE_RETRIES - 1:
                    await asyncio.sleep(1.0)

        raise EmbeddingError(
            f"Atlas Vector Search storage failed after {self.MAX_STORAGE_RETRIES} retries: {last_error}"
        )

    @staticmethod
    def _batch_chunks(chunks: list[Chunk]) -> list[list[Chunk]]:
        """Split chunks into batches of BATCH_SIZE.

        Pure function that partitions the input list into sublists of
        at most BATCH_SIZE elements.

        Args:
            chunks: Full list of chunks to partition.

        Returns:
            List of batches, each containing at most BATCH_SIZE chunks.
        """
        batch_size = EmbedderService.BATCH_SIZE
        return [
            chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)
        ]

    @staticmethod
    def _calculate_backoff(retry_num: int) -> float:
        """Calculate the backoff delay for a given retry attempt.

        Uses exponential backoff: min(2^n * BACKOFF_BASE, BACKOFF_CAP)
        where n is the zero-indexed retry number.

        Args:
            retry_num: Zero-indexed retry attempt number.

        Returns:
            Delay in seconds before the next retry.
        """
        delay = (2**retry_num) * EmbedderService.BACKOFF_BASE
        return min(delay, EmbedderService.BACKOFF_CAP)
