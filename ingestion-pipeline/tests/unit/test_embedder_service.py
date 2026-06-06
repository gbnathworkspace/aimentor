"""Property-based tests for EmbedderService batch logic and backoff calculation."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.schemas import Chunk, ChunkMetadata
from app.services.embedder_service import EmbedderService


@st.composite
def chunk_list(draw):
    """Generate a list of Chunk objects of varying size."""
    n = draw(st.integers(min_value=1, max_value=100))
    chunks = []
    for i in range(n):
        chunk = Chunk(
            text=f"chunk text {i}",
            metadata=ChunkMetadata(
                user_id="user-1",
                source="resume",
                section="skills",
                chunk_index=i,
            ),
        )
        chunks.append(chunk)
    return chunks


# Feature: ingestion-pipeline, Property 13: Embedding batch size invariant
class TestEmbeddingBatchSizeInvariant:
    """Property 13: Embedding batch size invariant.

    N chunks → ⌈N/20⌉ batches, each ≤20, union equals original.
    """

    @given(chunks=chunk_list())
    @settings(max_examples=100)
    def test_batch_partitioning_correct(self, chunks: list[Chunk]):
        """**Validates: Requirements 7.2**

        N chunks partitioned into ⌈N/20⌉ batches, each ≤20 chunks,
        union equals original set.
        """
        batches = EmbedderService._batch_chunks(chunks)

        n = len(chunks)
        expected_num_batches = math.ceil(n / 20)

        # Correct number of batches
        assert len(batches) == expected_num_batches

        # Each batch has at most 20 chunks
        for batch in batches:
            assert len(batch) <= 20

        # Union of all batches equals the original list
        all_chunks = []
        for batch in batches:
            all_chunks.extend(batch)
        assert len(all_chunks) == len(chunks)

        # Order preserved
        for i, chunk in enumerate(all_chunks):
            assert chunk.text == chunks[i].text

    @given(n=st.integers(min_value=0, max_value=0))
    @settings(max_examples=100)
    def test_empty_input_returns_empty(self, n):
        """Empty input returns empty batches."""
        batches = EmbedderService._batch_chunks([])
        assert batches == []


# Feature: ingestion-pipeline, Property 14: Exponential backoff calculation
class TestExponentialBackoffCalculation:
    """Property 14: Exponential backoff calculation.

    For n ∈ {0, 1, 2}, delay = min(2^n * 1, 8).
    """

    @given(retry_num=st.integers(min_value=0, max_value=2))
    @settings(max_examples=100)
    def test_backoff_formula_correct(self, retry_num: int):
        """**Validates: Requirements 7.4**

        For retry attempt n ∈ {0,1,2}, delay = min(2^n * 1, 8) seconds.
        """
        delay = EmbedderService._calculate_backoff(retry_num)
        expected = min(2**retry_num * EmbedderService.BACKOFF_BASE, EmbedderService.BACKOFF_CAP)
        assert delay == expected

    @given(retry_num=st.integers(min_value=0, max_value=20))
    @settings(max_examples=100)
    def test_backoff_never_exceeds_cap(self, retry_num: int):
        """Backoff delay never exceeds the cap of 8 seconds."""
        delay = EmbedderService._calculate_backoff(retry_num)
        assert delay <= EmbedderService.BACKOFF_CAP
        assert delay >= EmbedderService.BACKOFF_BASE
