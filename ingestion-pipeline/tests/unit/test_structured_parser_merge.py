"""Unit tests for StructuredParser session merge logic.

Tests the merge behavior for session uploads:
- _merge_profile_fields: non-null overwrite semantics
- _merge_leetcode_signals: additive sum semantics
"""

import pytest

from app.services.structured_parser import StructuredParser


class TestMergeProfileFields:
    """Tests for _merge_profile_fields (session Core Profile merge)."""

    def test_all_non_null_fields_included(self):
        """All non-null fields are included in the merge output."""
        profile_data = {
            "current_role": "Senior Engineer",
            "years_of_experience": 8,
            "education": "MS Computer Science",
            "skills": ["Python", "Go", "Rust"],
        }
        result = StructuredParser._merge_profile_fields(profile_data)
        assert result == profile_data

    def test_null_fields_excluded(self):
        """Null fields are excluded, preserving existing DB values."""
        profile_data = {
            "current_role": "Staff Engineer",
            "years_of_experience": None,
            "education": None,
            "skills": [],
        }
        result = StructuredParser._merge_profile_fields(profile_data)
        assert result == {"current_role": "Staff Engineer"}

    def test_all_null_returns_empty(self):
        """If all fields are null/empty, returns empty dict (no update)."""
        profile_data = {
            "current_role": None,
            "years_of_experience": None,
            "education": None,
            "skills": [],
        }
        result = StructuredParser._merge_profile_fields(profile_data)
        assert result == {}

    def test_empty_skills_list_treated_as_null(self):
        """An empty skills list is treated as null (no overwrite)."""
        profile_data = {
            "current_role": None,
            "years_of_experience": 5,
            "education": None,
            "skills": [],
        }
        result = StructuredParser._merge_profile_fields(profile_data)
        assert "skills" not in result
        assert result == {"years_of_experience": 5}

    def test_non_empty_skills_list_included(self):
        """A non-empty skills list is included in the merge output."""
        profile_data = {
            "current_role": None,
            "years_of_experience": None,
            "education": None,
            "skills": ["TypeScript"],
        }
        result = StructuredParser._merge_profile_fields(profile_data)
        assert result == {"skills": ["TypeScript"]}

    def test_mixed_null_and_non_null(self):
        """Only non-null fields are included in mixed scenarios."""
        profile_data = {
            "current_role": "Tech Lead",
            "years_of_experience": None,
            "education": "PhD",
            "skills": ["ML", "Python"],
        }
        result = StructuredParser._merge_profile_fields(profile_data)
        assert result == {
            "current_role": "Tech Lead",
            "education": "PhD",
            "skills": ["ML", "Python"],
        }


class TestMergeLeetCodeSignals:
    """Tests for _merge_leetcode_signals (session LeetCode additive merge)."""

    def test_sums_counts_for_existing_topic(self):
        """Counts are summed per difficulty for existing topics."""
        existing = {
            "leetcode_solved": {"easy": 5, "medium": 3, "hard": 1}
        }
        new = {
            "leetcode_solved": {"easy": 2, "medium": 4, "hard": 2}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 7, "medium": 7, "hard": 3}

    def test_existing_zero_counts(self):
        """New counts are added to existing zeros."""
        existing = {
            "leetcode_solved": {"easy": 0, "medium": 0, "hard": 0}
        }
        new = {
            "leetcode_solved": {"easy": 10, "medium": 5, "hard": 2}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 10, "medium": 5, "hard": 2}

    def test_new_zero_counts_preserve_existing(self):
        """Zero new counts don't reduce existing counts."""
        existing = {
            "leetcode_solved": {"easy": 8, "medium": 4, "hard": 2}
        }
        new = {
            "leetcode_solved": {"easy": 0, "medium": 0, "hard": 0}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 8, "medium": 4, "hard": 2}

    def test_missing_existing_leetcode_solved(self):
        """If existing signals have no leetcode_solved, new counts become the values."""
        existing = {}
        new = {
            "leetcode_solved": {"easy": 3, "medium": 2, "hard": 1}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 3, "medium": 2, "hard": 1}

    def test_preserves_other_signal_fields(self):
        """Other signal fields (like mentor_eval_score) are preserved."""
        existing = {
            "leetcode_solved": {"easy": 5, "medium": 3, "hard": 1},
            "mentor_eval_score": "B+",
            "mentor_eval_count": 3,
        }
        new = {
            "leetcode_solved": {"easy": 2, "medium": 1, "hard": 0}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 7, "medium": 4, "hard": 1}
        assert result["mentor_eval_score"] == "B+"
        assert result["mentor_eval_count"] == 3

    def test_partial_existing_counts(self):
        """Handles missing difficulty keys in existing signals gracefully."""
        existing = {
            "leetcode_solved": {"easy": 5}  # missing medium and hard
        }
        new = {
            "leetcode_solved": {"easy": 1, "medium": 2, "hard": 3}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 6, "medium": 2, "hard": 3}

    def test_no_new_leetcode_signals(self):
        """If new signals have no leetcode_solved, existing signals are preserved unchanged."""
        existing = {
            "leetcode_solved": {"easy": 5, "medium": 3, "hard": 1}
        }
        new = {}
        result = StructuredParser._merge_leetcode_signals(existing, new)
        assert result["leetcode_solved"] == {"easy": 5, "medium": 3, "hard": 1}

    def test_never_reduces_counts(self):
        """Even with large new counts, existing values are never reduced."""
        existing = {
            "leetcode_solved": {"easy": 100, "medium": 50, "hard": 25}
        }
        new = {
            "leetcode_solved": {"easy": 5, "medium": 3, "hard": 1}
        }
        result = StructuredParser._merge_leetcode_signals(existing, new)
        # All counts should be >= existing
        assert result["leetcode_solved"]["easy"] >= 100
        assert result["leetcode_solved"]["medium"] >= 50
        assert result["leetcode_solved"]["hard"] >= 25
