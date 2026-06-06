"""Tests for IngestionRouter: content routing and path execution."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.schemas import Chunk, ChunkMetadata, LeetCodeTopicStats, ResumeSection
from app.services.extractor_service import ExtractionResult
from app.services.ingestion_router import (
    IngestionRouter,
    RoutedContent,
    STRUCTURED_SECTIONS,
    NARRATIVE_SECTIONS,
)


# Strategies for generating ExtractionResult content
topic_names = st.sampled_from(["Arrays", "Trees", "Graphs", "DP", "Sorting"])

leetcode_stats_strategy = st.lists(
    st.builds(
        LeetCodeTopicStats,
        topic=topic_names,
        easy=st.integers(min_value=0, max_value=50),
        medium=st.integers(min_value=0, max_value=50),
        hard=st.integers(min_value=0, max_value=50),
    ),
    min_size=0,
    max_size=5,
)

# Section names that are routable
known_section_names = st.sampled_from(["work_experience", "skills", "education", "projects"])
# Unrecognized section names
unknown_section_names = st.sampled_from(["hobbies", "references", "certifications", "summary", "awards"])
# All section names
all_section_names = st.one_of(known_section_names, unknown_section_names)


resume_section_strategy = st.builds(
    ResumeSection,
    section=all_section_names,
    text=st.text(min_size=5, max_size=100).filter(lambda t: t.strip()),
    order=st.integers(min_value=0, max_value=10),
    sub_entries=st.just([]),
)


@st.composite
def extraction_result_strategy(draw):
    """Generate an ExtractionResult with optional leetcode stats and resume sections."""
    has_leetcode = draw(st.booleans())
    has_resume = draw(st.booleans())

    leetcode = draw(leetcode_stats_strategy) if has_leetcode else None
    # Make sure we have at least an empty list, not None, if flag is set
    if has_leetcode and not leetcode:
        leetcode = None

    sections = draw(st.lists(resume_section_strategy, min_size=1, max_size=6)) if has_resume else None
    if has_resume and not sections:
        sections = None

    return ExtractionResult(
        resume_sections=sections,
        leetcode_stats=leetcode,
    )


# Feature: ingestion-pipeline, Property 6: Content routing correctness
class TestContentRoutingCorrectness:
    """Property 6: Content routing correctness.

    For any ExtractionResult, verify routing rules:
    - LeetCode → structured only
    - work_experience → both structured and narrative
    - skills → structured only
    - education → structured only
    - projects → narrative only
    - unrecognized → neither path
    """

    @given(extraction_result=extraction_result_strategy())
    @settings(max_examples=100)
    def test_routing_rules_applied_correctly(self, extraction_result: ExtractionResult):
        """**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.7**

        For any extraction result, the ingestion router routes content correctly
        according to the defined rules.
        """
        router = IngestionRouter()
        routed = router._route_content(extraction_result)

        # (a) LeetCode aggregates appear only in structured path
        if extraction_result.leetcode_stats:
            assert routed.structured_leetcode == extraction_result.leetcode_stats
        else:
            assert routed.structured_leetcode is None

        # LeetCode never appears in narrative
        # (narrative only contains ResumeSection objects, not LeetCodeTopicStats)

        # Check resume section routing
        if extraction_result.resume_sections:
            structured_section_names = set()
            narrative_section_names = set()

            if routed.structured_sections:
                structured_section_names = {s.section.lower().strip() for s in routed.structured_sections}
            if routed.narrative_sections:
                narrative_section_names = {s.section.lower().strip() for s in routed.narrative_sections}

            for section in extraction_result.resume_sections:
                name = section.section.lower().strip()

                if name in STRUCTURED_SECTIONS and name in NARRATIVE_SECTIONS:
                    # (b) work_experience → both paths
                    assert name in structured_section_names, f"{name} should be in structured"
                    assert name in narrative_section_names, f"{name} should be in narrative"
                elif name in STRUCTURED_SECTIONS:
                    # (c) skills, education → structured only
                    assert name in structured_section_names, f"{name} should be in structured"
                    assert name not in narrative_section_names, f"{name} should NOT be in narrative"
                elif name in NARRATIVE_SECTIONS:
                    # (d) projects → narrative only
                    assert name not in structured_section_names, f"{name} should NOT be in structured"
                    assert name in narrative_section_names, f"{name} should be in narrative"
                else:
                    # (f) unrecognized → neither path
                    assert name not in structured_section_names, f"unrecognized '{name}' should NOT be in structured"
                    assert name not in narrative_section_names, f"unrecognized '{name}' should NOT be in narrative"


# ---------------------------------------------------------------------------
# Path execution tests
# ---------------------------------------------------------------------------

def _make_section(name: str, text: str = "sample content here") -> ResumeSection:
    return ResumeSection(section=name, text=text, order=0)


def _make_chunk() -> Chunk:
    return Chunk(
        text="sample chunk",
        metadata=ChunkMetadata(user_id="u1", source="resume", chunk_index=0),
    )


class TestStructuredPathExecution:
    """_run_structured_path calls StructuredParser with the right arguments."""

    @pytest.mark.asyncio
    async def test_calls_structured_parser_with_leetcode_stats(self):
        router = IngestionRouter()
        routed = RoutedContent(
            structured_leetcode=[LeetCodeTopicStats(topic="graphs", easy=2, medium=1, hard=0)],
            structured_sections=None,
            narrative_sections=None,
        )

        with patch(
            "app.services.ingestion_router.StructuredParser"
        ) as MockParser:
            instance = MockParser.return_value
            instance.process = AsyncMock()

            await router._run_structured_path(routed, user_id="u1", job_id="j1")

            instance.process.assert_awaited_once_with(
                leetcode_stats=routed.structured_leetcode,
                resume_sections=None,
                user_id="u1",
                job_id="j1",
            )

    @pytest.mark.asyncio
    async def test_calls_structured_parser_with_resume_sections(self):
        router = IngestionRouter()
        section = _make_section("work_experience")
        routed = RoutedContent(
            structured_leetcode=None,
            structured_sections=[section],
            narrative_sections=None,
        )

        with patch(
            "app.services.ingestion_router.StructuredParser"
        ) as MockParser:
            instance = MockParser.return_value
            instance.process = AsyncMock()

            await router._run_structured_path(routed, user_id="u1", job_id="j1")

            instance.process.assert_awaited_once_with(
                leetcode_stats=None,
                resume_sections=[section],
                user_id="u1",
                job_id="j1",
            )

    @pytest.mark.asyncio
    async def test_skips_parser_when_nothing_to_process(self):
        router = IngestionRouter()
        routed = RoutedContent(
            structured_leetcode=None,
            structured_sections=None,
            narrative_sections=None,
        )

        with patch(
            "app.services.ingestion_router.StructuredParser"
        ) as MockParser:
            await router._run_structured_path(routed, user_id="u1", job_id="j1")
            MockParser.assert_not_called()


class TestNarrativePathExecution:
    """_run_narrative_path calls ChunkerService → EmbedderService in order."""

    @pytest.mark.asyncio
    async def test_chunks_then_embeds(self):
        router = IngestionRouter()
        section = _make_section("work_experience", "Built payment gateway at Razorpay.")
        routed = RoutedContent(narrative_sections=[section])
        chunk = _make_chunk()

        with (
            patch("app.services.ingestion_router.ChunkerService") as MockChunker,
            patch("app.services.ingestion_router.EmbedderService") as MockEmbedder,
        ):
            MockChunker.return_value.chunk = MagicMock(return_value=[chunk])
            MockEmbedder.return_value.embed_and_store = AsyncMock()

            await router._run_narrative_path(routed, user_id="u1", job_id="j1")

            MockChunker.return_value.chunk.assert_called_once_with(
                sections=[section],
                user_id="u1",
                source="resume",
                job_id="j1",
            )
            MockEmbedder.return_value.embed_and_store.assert_awaited_once_with([chunk])

    @pytest.mark.asyncio
    async def test_skips_embedder_when_no_narrative_sections(self):
        router = IngestionRouter()
        routed = RoutedContent(narrative_sections=None)

        with (
            patch("app.services.ingestion_router.ChunkerService") as MockChunker,
            patch("app.services.ingestion_router.EmbedderService") as MockEmbedder,
        ):
            await router._run_narrative_path(routed, user_id="u1", job_id="j1")
            MockChunker.assert_not_called()
            MockEmbedder.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_embedder_when_chunker_produces_no_chunks(self):
        router = IngestionRouter()
        section = _make_section("projects", "  ")  # blank text → zero chunks
        routed = RoutedContent(narrative_sections=[section])

        with (
            patch("app.services.ingestion_router.ChunkerService") as MockChunker,
            patch("app.services.ingestion_router.EmbedderService") as MockEmbedder,
        ):
            MockChunker.return_value.chunk = MagicMock(return_value=[])

            await router._run_narrative_path(routed, user_id="u1", job_id="j1")

            MockEmbedder.return_value.embed_and_store.assert_not_called()
