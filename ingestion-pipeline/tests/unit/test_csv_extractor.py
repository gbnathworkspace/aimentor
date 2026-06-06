"""Property-based tests for CSV extraction and validation."""

import io
from collections import Counter

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.extractors.csv_extractor import (
    CSVExtractor,
    CSVExtractionError,
    REQUIRED_COLUMNS,
    VALID_DIFFICULTIES,
    VALID_STATUSES,
)


# Strategies for generating valid CSV data
valid_topics = st.sampled_from(["Arrays", "Trees", "Graphs", "Dynamic Programming", "Sorting", "Hashing"])
valid_statuses = st.sampled_from(["Accepted", "Solved", "accepted", "solved", "ACCEPTED", "SOLVED"])
valid_difficulties = st.sampled_from(["Easy", "Medium", "Hard", "easy", "medium", "hard", "EASY", "MEDIUM", "HARD"])
titles = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=" -"),
    min_size=3,
    max_size=30,
).filter(lambda t: t.strip())


@st.composite
def csv_row(draw):
    """Generate a single valid CSV row as a dict."""
    return {
        "title": draw(titles),
        "difficulty": draw(valid_difficulties),
        "status": draw(valid_statuses),
        "topic": draw(valid_topics),
    }


@st.composite
def valid_csv_bytes(draw):
    """Generate CSV bytes with valid required columns and random rows."""
    rows = draw(st.lists(csv_row(), min_size=1, max_size=30))

    lines = ["title,difficulty,status,topic"]
    for row in rows:
        lines.append(f"{row['title']},{row['difficulty']},{row['status']},{row['topic']}")

    csv_content = "\n".join(lines)
    return csv_content.encode("utf-8"), rows


# Feature: ingestion-pipeline, Property 4: CSV aggregation correctness
class TestCSVAggregationCorrectness:
    """Property 4: CSV aggregation correctness.

    For any valid CSV with required columns, the aggregated output per topic equals
    the filtered, grouped count by (topic, difficulty).
    """

    @given(data=valid_csv_bytes())
    @settings(max_examples=100)
    def test_aggregation_matches_manual_computation(self, data):
        """**Validates: Requirements 3.4, 3.5, 3.6, 3.7, 3.8**

        For any valid CSV, aggregated output per topic equals the count of rows
        where status is Accepted/Solved, difficulty is Easy/Medium/Hard, topic is non-empty,
        grouped by topic and difficulty.
        """
        csv_bytes, rows = data

        extractor = CSVExtractor()
        result = extractor.extract(csv_bytes)

        # Manually compute expected counts
        expected: dict[str, dict[str, int]] = {}
        for row in rows:
            status_lower = row["status"].lower().strip()
            difficulty_lower = row["difficulty"].lower().strip()
            topic = row["topic"].strip()

            if status_lower not in VALID_STATUSES:
                continue
            if difficulty_lower not in VALID_DIFFICULTIES:
                continue
            if not topic:
                continue

            if topic not in expected:
                expected[topic] = {"easy": 0, "medium": 0, "hard": 0}
            expected[topic][difficulty_lower] += 1

        # Compare with extractor result
        result_dict = {stat.topic: {"easy": stat.easy, "medium": stat.medium, "hard": stat.hard} for stat in result}

        assert len(result_dict) == len(expected)
        for topic, counts in expected.items():
            assert topic in result_dict, f"Topic '{topic}' missing from result"
            assert result_dict[topic] == counts, f"Mismatch for topic '{topic}'"


# Feature: ingestion-pipeline, Property 5: CSV required column validation
class TestCSVRequiredColumnValidation:
    """Property 5: CSV required column validation.

    For any subset of columns, the validator accepts iff all 4 required columns
    are present. Error lists exactly the missing ones.
    """

    @given(
        columns=st.sets(
            st.sampled_from(["title", "difficulty", "status", "topic"]),
            min_size=0,
            max_size=4,
        )
    )
    @settings(max_examples=100)
    def test_validation_accepts_iff_all_columns_present(self, columns: set):
        """**Validates: Requirements 3.2, 3.3**

        For any subset of columns from {title, difficulty, status, topic},
        the validator accepts iff all 4 are present. Error lists exactly the missing ones.
        """
        # Build a minimal CSV with only the selected columns
        header = ",".join(sorted(columns)) if columns else "empty"
        # Add a dummy row
        row_values = ",".join(["dummy"] * len(columns)) if columns else "x"
        csv_content = f"{header}\n{row_values}".encode("utf-8")

        extractor = CSVExtractor()

        if columns == REQUIRED_COLUMNS:
            # Should NOT raise - all columns present
            # Note: may raise other errors during extraction (e.g. invalid status)
            # but should NOT raise CSVExtractionError about missing columns
            try:
                extractor.extract(csv_content)
            except CSVExtractionError as e:
                # If it raises, it should NOT be about missing columns
                assert len(e.missing_columns) == 0, (
                    f"Should not complain about missing columns when all present, got: {e.missing_columns}"
                )
        else:
            # Should raise CSVExtractionError with exactly the missing columns
            missing_expected = sorted(REQUIRED_COLUMNS - columns)
            try:
                extractor.extract(csv_content)
                # If no exception, there's an issue - but only if columns are truly missing
                assert False, f"Expected CSVExtractionError for missing columns: {missing_expected}"
            except CSVExtractionError as e:
                assert sorted(e.missing_columns) == missing_expected
