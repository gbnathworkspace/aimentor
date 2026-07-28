"""Unit tests for document-upload source tagging on PendingProfileChange.

Validates that:
- PendingProfileChange entries can be created with source_type="document_upload"
  and session_id=job_id (Task 1.3, Requirements 5.1, 5.4)
- The existing accept_pending_change path works with document-upload tagged entries
- The existing dismiss_pending_change path works with document-upload tagged entries
- The new FOCUS_AREA proposable field is accepted and appended correctly
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.profile import PendingProfileChange, ProposableField


class TestPendingProfileChangeSourceType:
    """source_type field on PendingProfileChange."""

    def test_source_type_defaults_to_none(self):
        change = PendingProfileChange(
            field=ProposableField.STYLE_NOTE,
            proposed_value={"category": "pacing", "note": "Prefers fast pace"},
            reason="Inferred from session",
            session_id="session-abc",
            created_at=datetime.now(timezone.utc),
        )
        assert change.source_type is None

    def test_source_type_document_upload(self):
        change = PendingProfileChange(
            field=ProposableField.FOCUS_AREA,
            proposed_value={"value": "System Design"},
            reason="Extracted from resume.pdf",
            session_id="job-uuid-123",
            source_type="document_upload",
            created_at=datetime.now(timezone.utc),
        )
        assert change.source_type == "document_upload"
        assert change.session_id == "job-uuid-123"
        assert change.field == ProposableField.FOCUS_AREA

    def test_source_type_serializes_correctly(self):
        change = PendingProfileChange(
            field=ProposableField.FOCUS_AREA,
            proposed_value={"value": "System Design"},
            reason="From uploaded notes",
            session_id="job-456",
            source_type="document_upload",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        data = change.model_dump(mode="json")
        assert data["source_type"] == "document_upload"
        assert data["session_id"] == "job-456"

    def test_source_type_none_not_in_serialized_when_excluded(self):
        change = PendingProfileChange(
            field=ProposableField.STYLE_NOTE,
            proposed_value={"category": "communication", "note": "Likes examples"},
            reason="Observed in session",
            session_id="session-xyz",
            created_at=datetime.now(timezone.utc),
        )
        data = change.model_dump(mode="json")
        # source_type is present but None — existing code that doesn't use it is unaffected
        assert data["source_type"] is None


class TestFocusAreaProposableField:
    """FOCUS_AREA enum value in ProposableField."""

    def test_focus_area_in_proposable_fields(self):
        assert "focus_area" in {f.value for f in ProposableField}

    def test_create_focus_area_pending_change(self):
        change = PendingProfileChange(
            field=ProposableField.FOCUS_AREA,
            proposed_value={"value": "Distributed Systems"},
            reason="Resume mentions distributed systems experience",
            session_id="job-789",
            source_type="document_upload",
            created_at=datetime.now(timezone.utc),
        )
        assert change.field == ProposableField.FOCUS_AREA
        assert change.proposed_value == {"value": "Distributed Systems"}


class TestAcceptPendingChangeWithDocUpload:
    """accept_pending_change works with document-upload tagged entries."""

    @pytest.mark.asyncio
    async def test_accept_focus_area_appends_to_list(self):
        from app.routers.profile import accept_pending_change

        doc_with_pending = {
            "user_id": "user-1",
            "focus_areas": ["Python", "AWS"],
            "pending_changes": [
                {
                    "field": "focus_area",
                    "proposed_value": {"value": "System Design"},
                    "reason": "Extracted from JD",
                    "session_id": "job-abc",
                    "source_type": "document_upload",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
        result_doc = {**doc_with_pending, "focus_areas": ["Python", "AWS", "System Design"], "pending_changes": []}

        with patch("app.routers.profile.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value=doc_with_pending)
            mock_col.return_value.find_one_and_update = AsyncMock(return_value=result_doc)

            with patch("app.routers.profile.require_auth", return_value="user-1"):
                result = await accept_pending_change(field="focus_area", user_id="user-1")

            # Verify update was called with focus_areas including the new entry
            update_call = mock_col.return_value.find_one_and_update.call_args
            update_set = update_call.args[1]["$set"]
            assert "System Design" in update_set["focus_areas"]
            assert "Python" in update_set["focus_areas"]
            assert "AWS" in update_set["focus_areas"]

    @pytest.mark.asyncio
    async def test_accept_focus_area_deduplicates_case_insensitive(self):
        from app.routers.profile import accept_pending_change

        doc_with_pending = {
            "user_id": "user-1",
            "focus_areas": ["python", "AWS"],
            "pending_changes": [
                {
                    "field": "focus_area",
                    "proposed_value": {"value": "Python"},  # duplicate (case-insensitive)
                    "reason": "From document",
                    "session_id": "job-abc",
                    "source_type": "document_upload",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
        result_doc = {**doc_with_pending, "pending_changes": []}

        with patch("app.routers.profile.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value=doc_with_pending)
            mock_col.return_value.find_one_and_update = AsyncMock(return_value=result_doc)

            await accept_pending_change(field="focus_area", user_id="user-1")

            update_call = mock_col.return_value.find_one_and_update.call_args
            update_set = update_call.args[1]["$set"]
            # Should NOT have added "Python" since "python" already exists
            assert update_set["focus_areas"] == ["python", "AWS"]

    @pytest.mark.asyncio
    async def test_accept_document_upload_style_note_works(self):
        """Document-upload sourced style_note proposals go through the same path."""
        from app.routers.profile import accept_pending_change

        doc_with_pending = {
            "user_id": "user-1",
            "style_notes": [],
            "pending_changes": [
                {
                    "field": "style_note",
                    "proposed_value": {"category": "motivation", "note": "Responds to real examples"},
                    "reason": "Multiple references in uploaded doc",
                    "session_id": "job-xyz",  # job_id stored here
                    "source_type": "document_upload",
                    "created_at": "2026-07-01T10:00:00+00:00",
                }
            ],
        }
        result_doc = {**doc_with_pending, "pending_changes": []}

        with patch("app.routers.profile.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value=doc_with_pending)
            mock_col.return_value.find_one_and_update = AsyncMock(return_value=result_doc)

            await accept_pending_change(field="style_note", user_id="user-1")

            update_call = mock_col.return_value.find_one_and_update.call_args
            update_set = update_call.args[1]["$set"]
            assert len(update_set["style_notes"]) == 1
            assert update_set["style_notes"][0]["note"] == "Responds to real examples"


class TestDismissPendingChangeWithDocUpload:
    """dismiss_pending_change works with document-upload tagged entries."""

    @pytest.mark.asyncio
    async def test_dismiss_focus_area_removes_pending(self):
        from app.routers.profile import dismiss_pending_change

        doc_with_pending = {
            "user_id": "user-1",
            "pending_changes": [
                {
                    "field": "focus_area",
                    "proposed_value": {"value": "ML Engineering"},
                    "reason": "From uploaded syllabus",
                    "session_id": "job-def",
                    "source_type": "document_upload",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
        result_doc = {**doc_with_pending, "pending_changes": []}

        with patch("app.routers.profile.profiles_col") as mock_col:
            mock_col.return_value.find_one = AsyncMock(return_value=doc_with_pending)
            mock_col.return_value.find_one_and_update = AsyncMock(return_value=result_doc)

            await dismiss_pending_change(field="focus_area", user_id="user-1")

            update_call = mock_col.return_value.find_one_and_update.call_args
            update_set = update_call.args[1]["$set"]
            assert update_set["pending_changes"] == []
