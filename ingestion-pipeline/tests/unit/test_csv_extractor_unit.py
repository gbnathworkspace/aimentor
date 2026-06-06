"""Unit tests for the CSVExtractor class."""

import pytest

from app.services.extractors.csv_extractor import CSVExtractionError, CSVExtractor


@pytest.fixture
def extractor():
    return CSVExtractor()


def _make_csv(rows: list[list[str]], headers: list[str] | None = None) -> bytes:
    """Helper to build CSV bytes from rows."""
    if headers is None:
        headers = ["title", "difficulty", "status", "topic"]
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines).encode("utf-8")


class TestColumnValidation:
    """Task 4.2: Required column validation."""

    def test_valid_columns_accepted(self, extractor):
        csv = _make_csv([["Two Sum", "Easy", "Accepted", "Arrays"]])
        result = extractor.extract(csv)
        assert len(result) == 1

    def test_missing_single_column_raises_error(self, extractor):
        csv = _make_csv(
            [["Two Sum", "Easy", "Accepted"]],
            headers=["title", "difficulty", "status"],
        )
        with pytest.raises(CSVExtractionError) as exc_info:
            extractor.extract(csv)
        assert "topic" in exc_info.value.missing_columns

    def test_missing_multiple_columns_lists_all(self, extractor):
        csv = _make_csv(
            [["Two Sum", "Easy"]],
            headers=["title", "difficulty"],
        )
        with pytest.raises(CSVExtractionError) as exc_info:
            extractor.extract(csv)
        assert set(exc_info.value.missing_columns) == {"status", "topic"}

    def test_case_insensitive_column_names(self, extractor):
        csv = _make_csv(
            [["Two Sum", "Easy", "Accepted", "Arrays"]],
            headers=["Title", "Difficulty", "Status", "Topic"],
        )
        result = extractor.extract(csv)
        assert len(result) == 1


class TestRowFiltering:
    """Task 4.3: Row filtering."""

    def test_accepted_status_included(self, extractor):
        csv = _make_csv([["Two Sum", "Easy", "Accepted", "Arrays"]])
        result = extractor.extract(csv)
        assert result[0].easy == 1

    def test_solved_status_included(self, extractor):
        csv = _make_csv([["Two Sum", "Easy", "Solved", "Arrays"]])
        result = extractor.extract(csv)
        assert result[0].easy == 1

    def test_other_status_excluded(self, extractor):
        csv = _make_csv([
            ["Two Sum", "Easy", "Attempted", "Arrays"],
            ["Three Sum", "Easy", "Accepted", "Arrays"],
        ])
        result = extractor.extract(csv)
        assert result[0].easy == 1

    def test_status_case_insensitive(self, extractor):
        csv = _make_csv([["Two Sum", "Easy", "ACCEPTED", "Arrays"]])
        result = extractor.extract(csv)
        assert result[0].easy == 1

    def test_unrecognized_difficulty_discarded(self, extractor):
        csv = _make_csv([
            ["Two Sum", "Expert", "Accepted", "Arrays"],
            ["Three Sum", "Easy", "Accepted", "Arrays"],
        ])
        result = extractor.extract(csv)
        assert result[0].easy == 1

    def test_difficulty_case_insensitive(self, extractor):
        csv = _make_csv([["Two Sum", "HARD", "Accepted", "Arrays"]])
        result = extractor.extract(csv)
        assert result[0].hard == 1

    def test_empty_topic_skipped(self, extractor):
        csv = _make_csv([
            ["Two Sum", "Easy", "Accepted", ""],
            ["Three Sum", "Easy", "Accepted", "Arrays"],
        ])
        result = extractor.extract(csv)
        assert len(result) == 1
        assert result[0].topic == "Arrays"


class TestAggregation:
    """Task 4.4: Aggregation."""

    def test_single_topic_all_difficulties(self, extractor):
        csv = _make_csv([
            ["P1", "Easy", "Accepted", "Arrays"],
            ["P2", "Medium", "Accepted", "Arrays"],
            ["P3", "Hard", "Accepted", "Arrays"],
            ["P4", "Easy", "Accepted", "Arrays"],
        ])
        result = extractor.extract(csv)
        assert len(result) == 1
        assert result[0].topic == "Arrays"
        assert result[0].easy == 2
        assert result[0].medium == 1
        assert result[0].hard == 1

    def test_multiple_topics(self, extractor):
        csv = _make_csv([
            ["P1", "Easy", "Accepted", "Arrays"],
            ["P2", "Medium", "Accepted", "DP"],
            ["P3", "Hard", "Accepted", "Arrays"],
        ])
        result = extractor.extract(csv)
        topics = {r.topic: r for r in result}
        assert "Arrays" in topics
        assert "DP" in topics
        assert topics["Arrays"].easy == 1
        assert topics["Arrays"].hard == 1
        assert topics["DP"].medium == 1

    def test_missing_difficulty_fills_zero(self, extractor):
        csv = _make_csv([["P1", "Easy", "Accepted", "Trees"]])
        result = extractor.extract(csv)
        assert result[0].medium == 0
        assert result[0].hard == 0

    def test_empty_csv_returns_empty_list(self, extractor):
        csv = _make_csv([])
        result = extractor.extract(csv)
        assert result == []

    def test_all_rows_filtered_returns_empty(self, extractor):
        csv = _make_csv([
            ["P1", "Easy", "Attempted", "Arrays"],
            ["P2", "Expert", "Accepted", "Arrays"],
        ])
        result = extractor.extract(csv)
        assert result == []
