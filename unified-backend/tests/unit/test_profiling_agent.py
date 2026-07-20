"""Unit tests for app/services/profiling_agent.py."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.profiling_agent import _validate_signal, propose_changes


class TestValidateSignal:
    """Malformed/unrecognized signals are dropped, not raised."""

    def test_valid_style_note(self):
        raw = {
            "field": "style_note",
            "proposed_value": {"category": "pacing", "note": "Rushes through basics"},
            "reason": "User said 'let's skip ahead' twice",
        }
        result = _validate_signal(raw, "session-1")
        assert result is not None
        assert result.field.value == "style_note"
        assert result.proposed_value == raw["proposed_value"]
        assert result.session_id == "session-1"

    def test_valid_goal_orientation(self):
        raw = {
            "field": "goal_orientation",
            "proposed_value": {"value": "mastery_approach"},
            "reason": "Kept asking 'why' rather than just wanting the right answer",
        }
        result = _validate_signal(raw, "session-1")
        assert result is not None
        assert result.proposed_value == {"value": "mastery_approach"}

    def test_valid_learning_context_structured(self):
        raw = {
            "field": "learning_context_structured",
            "proposed_value": {"seniority_level": "senior"},
            "reason": "Mentioned 8 years of experience",
        }
        result = _validate_signal(raw, "session-1")
        assert result is not None

    def test_rejects_unknown_field(self):
        raw = {"field": "goal", "proposed_value": {"value": "x"}, "reason": "r"}
        assert _validate_signal(raw, "session-1") is None

    def test_rejects_invalid_style_note_category(self):
        raw = {
            "field": "style_note",
            "proposed_value": {"category": "not-a-real-category", "note": "x"},
            "reason": "r",
        }
        assert _validate_signal(raw, "session-1") is None

    def test_rejects_missing_note_text(self):
        raw = {
            "field": "style_note",
            "proposed_value": {"category": "pacing"},
            "reason": "r",
        }
        assert _validate_signal(raw, "session-1") is None

    def test_rejects_invalid_goal_orientation_value(self):
        raw = {
            "field": "goal_orientation",
            "proposed_value": {"value": "not-a-real-orientation"},
            "reason": "r",
        }
        assert _validate_signal(raw, "session-1") is None

    def test_rejects_empty_structured_dict(self):
        raw = {"field": "learning_context_structured", "proposed_value": {}, "reason": "r"}
        assert _validate_signal(raw, "session-1") is None

    def test_rejects_missing_reason(self):
        raw = {
            "field": "goal_orientation",
            "proposed_value": {"value": "mastery_approach"},
        }
        assert _validate_signal(raw, "session-1") is None

    def test_rejects_non_dict_input(self):
        assert _validate_signal("not a dict", "session-1") is None
        assert _validate_signal(None, "session-1") is None

    def test_truncates_long_reason(self):
        raw = {
            "field": "goal_orientation",
            "proposed_value": {"value": "mastery_approach"},
            "reason": "x" * 500,
        }
        result = _validate_signal(raw, "session-1")
        assert result is not None
        assert len(result.reason) == 200


class TestProposeChanges:
    """propose_changes validates, dedupes by field, and never raises."""

    @pytest.mark.asyncio
    async def test_empty_signals_is_noop(self):
        with patch("app.services.profiling_agent.profiles_col") as mock_col:
            await propose_changes("u1", "s1", [])
        mock_col.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_invalid_signals_is_noop(self):
        with patch("app.services.profiling_agent.profiles_col") as mock_col:
            await propose_changes("u1", "s1", [{"field": "bogus"}])
        mock_col.assert_not_called()

    @pytest.mark.asyncio
    async def test_stores_valid_proposal(self):
        with patch("app.services.profiling_agent.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value={"pending_changes": []})
            mock_col.return_value.update_one = AsyncMock()

            await propose_changes("u1", "s1", [
                {
                    "field": "goal_orientation",
                    "proposed_value": {"value": "mastery_approach"},
                    "reason": "evidence",
                }
            ])

            mock_col.return_value.update_one.assert_called_once()
            call_args = mock_col.return_value.update_one.call_args.args
            new_pending = call_args[1]["$set"]["pending_changes"]
            assert len(new_pending) == 1
            assert new_pending[0]["field"] == "goal_orientation"

    @pytest.mark.asyncio
    async def test_replaces_existing_pending_for_same_field(self):
        existing_pending = [{
            "field": "goal_orientation",
            "proposed_value": {"value": "performance_approach"},
            "reason": "old evidence",
            "session_id": "s0",
            "created_at": "2026-01-01T00:00:00+00:00",
        }]
        with patch("app.services.profiling_agent.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value={"pending_changes": existing_pending})
            mock_col.return_value.update_one = AsyncMock()

            await propose_changes("u1", "s1", [
                {
                    "field": "goal_orientation",
                    "proposed_value": {"value": "mastery_approach"},
                    "reason": "new evidence",
                }
            ])

            call_args = mock_col.return_value.update_one.call_args.args
            new_pending = call_args[1]["$set"]["pending_changes"]
            assert len(new_pending) == 1
            assert new_pending[0]["proposed_value"] == {"value": "mastery_approach"}

    @pytest.mark.asyncio
    async def test_keeps_pending_for_other_fields(self):
        existing_pending = [{
            "field": "style_note",
            "proposed_value": {"category": "pacing", "note": "old note"},
            "reason": "old evidence",
            "session_id": "s0",
            "created_at": "2026-01-01T00:00:00+00:00",
        }]
        with patch("app.services.profiling_agent.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value={"pending_changes": existing_pending})
            mock_col.return_value.update_one = AsyncMock()

            await propose_changes("u1", "s1", [
                {
                    "field": "goal_orientation",
                    "proposed_value": {"value": "mastery_approach"},
                    "reason": "new evidence",
                }
            ])

            call_args = mock_col.return_value.update_one.call_args.args
            new_pending = call_args[1]["$set"]["pending_changes"]
            fields = {p["field"] for p in new_pending}
            assert fields == {"style_note", "goal_orientation"}

    @pytest.mark.asyncio
    async def test_never_raises_on_db_failure(self):
        with patch("app.services.profiling_agent.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(side_effect=Exception("DB down"))
            # Should not raise
            await propose_changes("u1", "s1", [
                {
                    "field": "goal_orientation",
                    "proposed_value": {"value": "mastery_approach"},
                    "reason": "evidence",
                }
            ])
