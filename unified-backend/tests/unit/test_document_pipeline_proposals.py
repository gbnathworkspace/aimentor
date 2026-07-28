"""Unit tests for document pipeline proposal creation and skip review mode.

Validates that:
- When skip_review=false: PendingProfileChange entries are created with correct
  source_type="document_upload" and session_id=job_id (Requirements 5.1, 5.4)
- When skip_review=true: proposals are written directly to L1 memory without
  creating pending changes (Requirement 5.7)
- Proposals are always stored on the Upload_Job record regardless of mode
  (Requirement 5.8)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.profile import ProposableField


class TestCreatePendingChanges:
    """_create_pending_changes creates PendingProfileChange entries."""

    @pytest.mark.asyncio
    async def test_creates_one_entry_per_proposal(self):
        from app.services.document_pipeline import _create_pending_changes

        proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "System Design"},
                "reason": "Extracted from resume.pdf",
            },
            {
                "field": "style_note",
                "proposed_value": {"category": "pacing", "note": "Prefers fast pace"},
                "reason": "Detected from uploaded document content",
            },
        ]

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _create_pending_changes("user-1", "job-abc", proposals)

            mock_collection.update_one.assert_called_once()
            call_args = mock_collection.update_one.call_args
            filter_doc = call_args.args[0]
            update_doc = call_args.args[1]

            assert filter_doc == {"user_id": "user-1"}
            pushed_entries = update_doc["$push"]["pending_changes"]["$each"]
            assert len(pushed_entries) == 2

    @pytest.mark.asyncio
    async def test_tags_with_source_type_and_session_id(self):
        from app.services.document_pipeline import _create_pending_changes

        proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "ML Engineering"},
                "reason": "From uploaded document",
            },
        ]

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _create_pending_changes("user-1", "job-xyz-789", proposals)

            call_args = mock_collection.update_one.call_args
            pushed_entries = call_args.args[1]["$push"]["pending_changes"]["$each"]
            entry = pushed_entries[0]

            assert entry["source_type"] == "document_upload"
            assert entry["session_id"] == "job-xyz-789"
            assert entry["field"] == "focus_area"
            assert entry["proposed_value"] == {"value": "ML Engineering"}

    @pytest.mark.asyncio
    async def test_preserves_requires_replacement_flag(self):
        from app.services.document_pipeline import _create_pending_changes

        proposals = [
            {
                "field": "style_note",
                "proposed_value": {"category": "pacing", "note": "Fast learner", "source_quote": "I learn fast"},
                "reason": "Style insight from document",
                "requires_replacement": True,
            },
        ]

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _create_pending_changes("user-1", "job-123", proposals)

            call_args = mock_collection.update_one.call_args
            pushed_entries = call_args.args[1]["$push"]["pending_changes"]["$each"]
            entry = pushed_entries[0]

            assert entry["requires_replacement"] is True

    @pytest.mark.asyncio
    async def test_noop_when_no_proposals(self):
        from app.services.document_pipeline import _create_pending_changes

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _create_pending_changes("user-1", "job-123", [])

            mock_collection.update_one.assert_not_called()


class TestApplyProposalsDirectly:
    """_apply_proposals_directly writes to L1 memory when skip_review=true."""

    @pytest.mark.asyncio
    async def test_appends_focus_area(self):
        from app.services.document_pipeline import _apply_proposals_directly

        proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "System Design"},
                "reason": "From document",
            },
        ]
        profile = {
            "user_id": "user-1",
            "focus_areas": ["Python", "AWS"],
            "style_notes": [],
        }

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.find_one = AsyncMock(return_value=profile)
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _apply_proposals_directly("user-1", proposals)

            call_args = mock_collection.update_one.call_args
            update_set = call_args.args[1]["$set"]
            assert "System Design" in update_set["focus_areas"]
            assert "Python" in update_set["focus_areas"]
            assert "AWS" in update_set["focus_areas"]

    @pytest.mark.asyncio
    async def test_focus_area_deduplicates_case_insensitive(self):
        from app.services.document_pipeline import _apply_proposals_directly

        proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "Python"},  # already exists as "python"
                "reason": "From document",
            },
        ]
        profile = {
            "user_id": "user-1",
            "focus_areas": ["python", "AWS"],
            "style_notes": [],
        }

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.find_one = AsyncMock(return_value=profile)
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _apply_proposals_directly("user-1", proposals)

            call_args = mock_collection.update_one.call_args
            update_set = call_args.args[1]["$set"]
            # Should NOT have added "Python" since "python" exists
            assert update_set["focus_areas"] == ["python", "AWS"]

    @pytest.mark.asyncio
    async def test_appends_style_note_with_cap(self):
        from app.services.document_pipeline import _apply_proposals_directly

        proposals = [
            {
                "field": "style_note",
                "proposed_value": {
                    "category": "motivation",
                    "note": "Likes real-world examples",
                    "source_quote": "I prefer hands-on...",
                },
                "reason": "From document",
            },
        ]
        # Profile already has 5 style notes (max cap)
        existing_notes = [
            {"category": "pacing", "note": f"Note {i}", "source_quote": "...", "session_id": "s", "added_at": "2026-01-01T00:00:00+00:00"}
            for i in range(5)
        ]
        profile = {
            "user_id": "user-1",
            "focus_areas": [],
            "style_notes": existing_notes,
        }

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.find_one = AsyncMock(return_value=profile)
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _apply_proposals_directly("user-1", proposals)

            call_args = mock_collection.update_one.call_args
            update_set = call_args.args[1]["$set"]
            # Should have 5 notes max (FIFO drop oldest)
            assert len(update_set["style_notes"]) == 5
            # Newest note is the last one
            assert update_set["style_notes"][-1]["note"] == "Likes real-world examples"

    @pytest.mark.asyncio
    async def test_noop_when_profile_not_found(self):
        from app.services.document_pipeline import _apply_proposals_directly

        proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "Kubernetes"},
                "reason": "From document",
            },
        ]

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.find_one = AsyncMock(return_value=None)
            mock_collection.update_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _apply_proposals_directly("user-1", proposals)

            mock_collection.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_when_no_proposals(self):
        from app.services.document_pipeline import _apply_proposals_directly

        with patch("app.services.document_pipeline.profiles_col") as mock_col:
            mock_collection = MagicMock()
            mock_collection.find_one = AsyncMock()
            mock_col.return_value = mock_collection

            await _apply_proposals_directly("user-1", [])

            mock_collection.find_one.assert_not_called()


class TestProcessDocumentUploadProposalModes:
    """Integration-level test of process_document_upload's proposal handling."""

    @pytest.mark.asyncio
    async def test_skip_review_false_creates_pending_changes(self):
        """When skip_review=false, proposals are routed to _create_pending_changes."""
        from app.services.document_pipeline import process_document_upload

        mock_extraction_result = MagicMock()
        mock_extraction_result.success = True
        mock_extraction_result.text = "Some extracted text"
        mock_extraction_result.error = None

        mock_synthesis_result = MagicMock()
        mock_synthesis_result.success = True
        mock_synthesis_result.proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "Backend Dev"},
                "reason": "From document",
            }
        ]
        mock_synthesis_result.error = None

        with (
            patch("app.services.document_pipeline.document_upload_jobs_col") as mock_jobs_col,
            patch("app.services.document_pipeline.extract_document", return_value=mock_extraction_result),
            patch("app.services.document_pipeline.synthesize_l1_facts", return_value=mock_synthesis_result),
            patch("app.services.document_pipeline._create_pending_changes") as mock_create,
            patch("app.services.document_pipeline._apply_proposals_directly") as mock_apply,
        ):
            mock_col_instance = MagicMock()
            mock_col_instance.update_one = AsyncMock()
            mock_jobs_col.return_value = mock_col_instance
            mock_create.return_value = None
            mock_apply.return_value = None

            # Make both async
            mock_create.side_effect = AsyncMock()
            mock_apply.side_effect = AsyncMock()

            await process_document_upload(
                job_id="job-1",
                user_id="user-1",
                file_paths=["/tmp/file.pdf"],
                mime_types=["application/pdf"],
                skip_review=False,
            )

            # _create_pending_changes should be called
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args.args[0] == "user-1" or call_args[0][0] == "user-1"

            # _apply_proposals_directly should NOT be called
            mock_apply.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_review_true_applies_directly(self):
        """When skip_review=true, proposals are routed to _apply_proposals_directly."""
        from app.services.document_pipeline import process_document_upload

        mock_extraction_result = MagicMock()
        mock_extraction_result.success = True
        mock_extraction_result.text = "Some extracted text"
        mock_extraction_result.error = None

        mock_synthesis_result = MagicMock()
        mock_synthesis_result.success = True
        mock_synthesis_result.proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "Backend Dev"},
                "reason": "From document",
            }
        ]
        mock_synthesis_result.error = None

        with (
            patch("app.services.document_pipeline.document_upload_jobs_col") as mock_jobs_col,
            patch("app.services.document_pipeline.extract_document", return_value=mock_extraction_result),
            patch("app.services.document_pipeline.synthesize_l1_facts", return_value=mock_synthesis_result),
            patch("app.services.document_pipeline._create_pending_changes") as mock_create,
            patch("app.services.document_pipeline._apply_proposals_directly") as mock_apply,
        ):
            mock_col_instance = MagicMock()
            mock_col_instance.update_one = AsyncMock()
            mock_jobs_col.return_value = mock_col_instance
            mock_create.side_effect = AsyncMock()
            mock_apply.side_effect = AsyncMock()

            await process_document_upload(
                job_id="job-2",
                user_id="user-1",
                file_paths=["/tmp/file.pdf"],
                mime_types=["application/pdf"],
                skip_review=True,
            )

            # _apply_proposals_directly should be called
            mock_apply.assert_called_once()

            # _create_pending_changes should NOT be called
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_proposals_stored_on_job_regardless_of_mode(self):
        """Proposals are stored on the Upload_Job record in both modes (Requirement 5.8)."""
        from app.services.document_pipeline import process_document_upload

        mock_extraction_result = MagicMock()
        mock_extraction_result.success = True
        mock_extraction_result.text = "Some text"
        mock_extraction_result.error = None

        expected_proposals = [
            {
                "field": "focus_area",
                "proposed_value": {"value": "DevOps"},
                "reason": "From doc",
            }
        ]
        mock_synthesis_result = MagicMock()
        mock_synthesis_result.success = True
        mock_synthesis_result.proposals = expected_proposals
        mock_synthesis_result.error = None

        for skip_review_val in [True, False]:
            with (
                patch("app.services.document_pipeline.document_upload_jobs_col") as mock_jobs_col,
                patch("app.services.document_pipeline.extract_document", return_value=mock_extraction_result),
                patch("app.services.document_pipeline.synthesize_l1_facts", return_value=mock_synthesis_result),
                patch("app.services.document_pipeline._create_pending_changes", new_callable=AsyncMock),
                patch("app.services.document_pipeline._apply_proposals_directly", new_callable=AsyncMock),
            ):
                mock_col_instance = MagicMock()
                mock_col_instance.update_one = AsyncMock()
                mock_jobs_col.return_value = mock_col_instance

                await process_document_upload(
                    job_id="job-3",
                    user_id="user-1",
                    file_paths=["/tmp/file.txt"],
                    mime_types=["text/plain"],
                    skip_review=skip_review_val,
                )

                # The last update_one call should be the "done" status with proposals
                last_call = mock_col_instance.update_one.call_args_list[-1]
                update_set = last_call.args[1]["$set"]
                assert update_set["status"] == "done"
                assert update_set["proposals"] == expected_proposals
                assert update_set["proposal_count"] == 1
