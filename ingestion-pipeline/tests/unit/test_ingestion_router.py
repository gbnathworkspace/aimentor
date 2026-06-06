"""Property-based tests for content routing correctness."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.schemas import LeetCodeTopicStats, ResumeSection
from app.services.extractor_service import ExtractionResult
from app.services.ingestion_router import (
    IngestionRouter,
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
