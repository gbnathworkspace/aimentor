"""Unit tests for accumulation logic and deduplication in l1_fact_synthesizer.

Tests cover:
- Focus area deduplication (case-insensitive exact match) — Requirement 7.2
- Style note cap detection and flagging — Requirements 7.3, 7.4
- Accumulation invariant (additive only, no overwrites) — Requirement 7.1
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.profile import ProposableField
from app.services.l1_fact_synthesizer import (
    MAX_STYLE_NOTES,
    accumulate_proposals,
    deduplicate_focus_areas,
    flag_style_notes_at_cap,
)


class TestDeduplicateFocusAreas:
    """Tests for case-insensitive focus area deduplication (Requirement 7.2)."""

    def test_no_duplicates_all_kept(self):
        proposed = ["System Design", "Backend Development"]
        existing = ["Frontend", "DevOps"]
        result = deduplicate_focus_areas(proposed, existing)
        assert result == ["System Design", "Backend Development"]

    def test_exact_case_match_removed(self):
        proposed = ["System Design", "Backend Development"]
        existing = ["System Design", "DevOps"]
        result = deduplicate_focus_areas(proposed, existing)
        assert result == ["Backend Development"]

    def test_case_insensitive_match_removed(self):
        proposed = ["system design", "BACKEND DEVELOPMENT"]
        existing = ["System Design", "Backend Development"]
        result = deduplicate_focus_areas(proposed, existing)
        assert result == []

    def test_mixed_case_partial_duplicates(self):
        proposed = ["System Design", "API Design", "backend development"]
        existing = ["system design", "Backend Development"]
        result = deduplicate_focus_areas(proposed, existing)
        assert result == ["API Design"]

    def test_empty_proposed_returns_empty(self):
        result = deduplicate_focus_areas([], ["System Design"])
        assert result == []

    def test_empty_existing_all_kept(self):
        proposed = ["System Design", "Backend"]
        result = deduplicate_focus_areas(proposed, [])
        assert result == ["System Design", "Backend"]

    def test_both_empty(self):
        result = deduplicate_focus_areas([], [])
        assert result == []

    def test_whitespace_not_normalized(self):
        """Only exact case-insensitive match — leading/trailing spaces are significant."""
        proposed = [" System Design ", "System Design"]
        existing = ["System Design"]
        result = deduplicate_focus_areas(proposed, existing)
        # " System Design " has leading/trailing space — NOT a match
        assert result == [" System Design "]

    def test_unicode_case_insensitive(self):
        """Case-insensitive works for basic ASCII."""
        proposed = ["PYTHON", "python", "Python"]
        existing = ["python"]
        result = deduplicate_focus_areas(proposed, existing)
        assert result == []


class TestFlagStyleNotesAtCap:
    """Tests for style note cap flagging (Requirements 7.3, 7.4)."""

    def test_below_cap_no_flags(self):
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "test"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=3)
        assert len(result) == 1
        assert "requires_replacement" not in result[0]

    def test_at_cap_flags_style_notes(self):
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "test"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=5)
        assert len(result) == 1
        assert result[0]["requires_replacement"] is True

    def test_above_cap_flags_style_notes(self):
        """Edge case: if somehow more than 5 exist, still flag."""
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "test"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=6)
        assert result[0]["requires_replacement"] is True

    def test_non_style_note_proposals_untouched(self):
        proposals = [
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Python"}, "reason": "r"},
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "SQL"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=5)
        assert len(result) == 2
        assert "requires_replacement" not in result[0]
        assert "requires_replacement" not in result[1]

    def test_mixed_proposals_only_style_notes_flagged(self):
        proposals = [
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Python"}, "reason": "r"},
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "test"}, "reason": "r"},
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "SQL"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=5)
        assert "requires_replacement" not in result[0]
        assert result[1]["requires_replacement"] is True
        assert "requires_replacement" not in result[2]

    def test_empty_proposals(self):
        result = flag_style_notes_at_cap([], existing_style_notes_count=5)
        assert result == []

    def test_exactly_at_max_style_notes(self):
        """When count equals MAX_STYLE_NOTES exactly."""
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "new"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=MAX_STYLE_NOTES)
        assert result[0]["requires_replacement"] is True

    def test_one_below_max_not_flagged(self):
        """When count is MAX_STYLE_NOTES - 1, no flag."""
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "new"}, "reason": "r"},
        ]
        result = flag_style_notes_at_cap(proposals, existing_style_notes_count=MAX_STYLE_NOTES - 1)
        assert "requires_replacement" not in result[0]


class TestAccumulateProposals:
    """Tests for the combined accumulate_proposals function (Requirements 7.1, 7.2, 7.3)."""

    @pytest.mark.asyncio
    async def test_empty_proposals_returns_empty(self):
        result = await accumulate_proposals([], "user-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_focus_area_dedup_removes_duplicates(self):
        proposals = [
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "System Design"}, "reason": "r"},
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Python"}, "reason": "r"},
        ]
        with patch(
            "app.services.l1_fact_synthesizer._get_user_profile_state",
            new_callable=AsyncMock,
            return_value={"focus_areas": ["system design"], "style_notes": []},
        ):
            result = await accumulate_proposals(proposals, "user-1")

        # "System Design" is a case-insensitive dup of "system design"
        assert len(result) == 1
        assert result[0]["proposed_value"]["value"] == "Python"

    @pytest.mark.asyncio
    async def test_style_notes_flagged_at_cap(self):
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "new insight"}, "reason": "r"},
        ]
        five_notes = [{"category": "pacing", "note": f"note {i}"} for i in range(5)]
        with patch(
            "app.services.l1_fact_synthesizer._get_user_profile_state",
            new_callable=AsyncMock,
            return_value={"focus_areas": [], "style_notes": five_notes},
        ):
            result = await accumulate_proposals(proposals, "user-1")

        assert len(result) == 1
        assert result[0]["requires_replacement"] is True

    @pytest.mark.asyncio
    async def test_style_notes_not_flagged_below_cap(self):
        proposals = [
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "new insight"}, "reason": "r"},
        ]
        three_notes = [{"category": "pacing", "note": f"note {i}"} for i in range(3)]
        with patch(
            "app.services.l1_fact_synthesizer._get_user_profile_state",
            new_callable=AsyncMock,
            return_value={"focus_areas": [], "style_notes": three_notes},
        ):
            result = await accumulate_proposals(proposals, "user-1")

        assert len(result) == 1
        assert "requires_replacement" not in result[0]

    @pytest.mark.asyncio
    async def test_combined_dedup_and_flagging(self):
        """Both dedup and flagging apply to a mixed set of proposals."""
        proposals = [
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Python"}, "reason": "r"},
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "SQL"}, "reason": "r"},
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "fast pace"}, "reason": "r"},
        ]
        five_notes = [{"category": "pacing", "note": f"note {i}"} for i in range(5)]
        with patch(
            "app.services.l1_fact_synthesizer._get_user_profile_state",
            new_callable=AsyncMock,
            return_value={"focus_areas": ["python"], "style_notes": five_notes},
        ):
            result = await accumulate_proposals(proposals, "user-1")

        # "Python" is deduplicated (existing has "python")
        # "SQL" is kept
        # Style note is flagged (5 existing)
        assert len(result) == 2
        fields = [p["field"] for p in result]
        assert ProposableField.FOCUS_AREA.value in fields
        assert ProposableField.STYLE_NOTE.value in fields

        # Verify the correct focus area survived
        focus_proposals = [p for p in result if p["field"] == ProposableField.FOCUS_AREA.value]
        assert len(focus_proposals) == 1
        assert focus_proposals[0]["proposed_value"]["value"] == "SQL"

        # Verify style note is flagged
        style_proposals = [p for p in result if p["field"] == ProposableField.STYLE_NOTE.value]
        assert style_proposals[0]["requires_replacement"] is True

    @pytest.mark.asyncio
    async def test_no_profile_found_empty_state(self):
        """When user has no profile, all proposals pass through without dedup or flags."""
        proposals = [
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Python"}, "reason": "r"},
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "fast"}, "reason": "r"},
        ]
        with patch(
            "app.services.l1_fact_synthesizer._get_user_profile_state",
            new_callable=AsyncMock,
            return_value={"focus_areas": [], "style_notes": []},
        ):
            result = await accumulate_proposals(proposals, "user-1")

        assert len(result) == 2
        assert "requires_replacement" not in result[1]

    @pytest.mark.asyncio
    async def test_proposals_are_additive_never_removes(self):
        """Accumulation NEVER removes non-duplicate proposals — only discards exact dups."""
        proposals = [
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Algorithms"}, "reason": "r"},
            {"field": ProposableField.FOCUS_AREA.value, "proposed_value": {"value": "Concurrency"}, "reason": "r"},
            {"field": ProposableField.STYLE_NOTE.value, "proposed_value": {"note": "prefers examples"}, "reason": "r"},
        ]
        with patch(
            "app.services.l1_fact_synthesizer._get_user_profile_state",
            new_callable=AsyncMock,
            return_value={"focus_areas": ["Data Structures"], "style_notes": []},
        ):
            result = await accumulate_proposals(proposals, "user-1")

        # None are duplicates, all should be kept
        assert len(result) == 3
