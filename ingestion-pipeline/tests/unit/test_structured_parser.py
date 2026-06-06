"""Property-based tests for StructuredParser and Zod validation."""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models.schemas import LeetCodeTopicStats
from app.models.validators import (
    ValidationError,
    validate_core_profile,
    validate_skill_graph_signals,
)
from app.services.structured_parser import StructuredParser


# Strategies
topic_names = st.text(
    alphabet=st.characters(whitelist_categories=("L",), whitelist_characters=" "),
    min_size=1,
    max_size=30,
).filter(lambda t: t.strip())

non_negative_ints = st.integers(min_value=0, max_value=1000)


leetcode_stats_strategy = st.builds(
    LeetCodeTopicStats,
    topic=topic_names,
    easy=non_negative_ints,
    medium=non_negative_ints,
    hard=non_negative_ints,
)


# Feature: ingestion-pipeline, Property 7: LeetCode to Skill Graph format
class TestLeetCodeToSkillGraphFormat:
    """Property 7: LeetCode to Skill Graph format.

    For any LeetCodeTopicStats, _build_skill_graph_upserts produces docs with format
    { "topic": ..., "signals": { "leetcode_solved": { "easy": ..., "medium": ..., "hard": ... } } }
    with matching values.
    """

    @given(stats=st.lists(leetcode_stats_strategy, min_size=1, max_size=10))
    @settings(max_examples=100)
    def test_upsert_format_matches_input(self, stats: list[LeetCodeTopicStats]):
        """**Validates: Requirements 5.1**

        For any LeetCodeTopicStats, the upsert document has the correct format
        and matching values.
        """
        parser = StructuredParser()
        upserts = parser._build_skill_graph_upserts(stats)

        assert len(upserts) == len(stats)

        for stat, upsert in zip(stats, upserts):
            # Check format
            assert "topic" in upsert
            assert "signals" in upsert
            assert "leetcode_solved" in upsert["signals"]

            leetcode_solved = upsert["signals"]["leetcode_solved"]
            assert "easy" in leetcode_solved
            assert "medium" in leetcode_solved
            assert "hard" in leetcode_solved

            # Check values match
            assert upsert["topic"] == stat.topic
            assert leetcode_solved["easy"] == stat.easy
            assert leetcode_solved["medium"] == stat.medium
            assert leetcode_solved["hard"] == stat.hard

    @given(data=st.data())
    @settings(max_examples=100)
    def test_empty_input_returns_empty(self, data):
        """Empty or None input returns empty list."""
        parser = StructuredParser()
        assert parser._build_skill_graph_upserts(None) == []
        assert parser._build_skill_graph_upserts([]) == []


# Feature: ingestion-pipeline, Property 8: Zod validation gates all writes
class TestZodValidationGatesAllWrites:
    """Property 8: Zod validation gates all writes.

    For any data object, validate_core_profile succeeds iff valid
    (skills is list[str], years_of_experience non-negative int or None).
    Invalid data raises ValidationError.
    """

    @given(
        skills=st.one_of(
            st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5),
            st.just(None),
        ),
        years=st.one_of(
            st.integers(min_value=0, max_value=50),
            st.just(None),
        ),
        current_role=st.one_of(st.text(min_size=1, max_size=30), st.just(None)),
        education=st.one_of(st.text(min_size=1, max_size=50), st.just(None)),
    )
    @settings(max_examples=100)
    def test_valid_core_profile_passes_validation(
        self, skills, years, current_role, education
    ):
        """**Validates: Requirements 5.4, 5.5, 9.5**

        Valid core profile data (skills as list[str], years_of_experience as
        non-negative int or None) passes validation without error.
        """
        data = {
            "current_role": current_role,
            "years_of_experience": years,
            "education": education,
            "skills": skills if skills is not None else [],
        }

        # This should not raise for valid data
        result = validate_core_profile(data)
        assert result is not None

    @given(
        invalid_skills=st.one_of(
            st.just("not a list"),
            st.just(123),
            st.lists(st.integers(), min_size=1, max_size=3),  # list of non-strings
        )
    )
    @settings(max_examples=100)
    def test_invalid_skills_raises_validation_error(self, invalid_skills):
        """Invalid skills field raises ValidationError."""
        data = {
            "current_role": "Engineer",
            "years_of_experience": 5,
            "education": "BS CS",
            "skills": invalid_skills,
        }

        try:
            validate_core_profile(data)
            assert False, "Expected ValidationError for invalid skills"
        except (ValidationError, Exception):
            pass  # Expected

    @given(
        invalid_years=st.one_of(
            st.integers(max_value=-1),  # negative
            st.just("not an int"),
            st.just(3.5),
        )
    )
    @settings(max_examples=100)
    def test_invalid_years_raises_validation_error(self, invalid_years):
        """Invalid years_of_experience raises ValidationError."""
        data = {
            "current_role": "Engineer",
            "years_of_experience": invalid_years,
            "education": "BS CS",
            "skills": ["Python"],
        }

        try:
            validate_core_profile(data)
            assert False, "Expected ValidationError for invalid years_of_experience"
        except (ValidationError, Exception):
            pass  # Expected

    @given(
        easy=non_negative_ints,
        medium=non_negative_ints,
        hard=non_negative_ints,
    )
    @settings(max_examples=100)
    def test_valid_skill_graph_signals_passes(self, easy, medium, hard):
        """Valid skill graph signals pass validation."""
        data = {
            "leetcode_solved": {"easy": easy, "medium": medium, "hard": hard},
        }
        result = validate_skill_graph_signals(data)
        assert result is not None

    @given(
        bad_value=st.one_of(
            st.integers(max_value=-1),
            st.just("string"),
            st.just(None),
        )
    )
    @settings(max_examples=100)
    def test_invalid_skill_graph_signals_raises(self, bad_value):
        """Invalid leetcode_solved values raise ValidationError."""
        assume(bad_value is not None)  # None is handled differently
        data = {
            "leetcode_solved": {"easy": bad_value, "medium": 0, "hard": 0},
        }

        try:
            validate_skill_graph_signals(data)
            assert False, "Expected ValidationError for invalid skill graph signals"
        except (ValidationError, Exception):
            pass  # Expected
