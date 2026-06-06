"""Unit tests for Job Status endpoint and Job Status State Machine."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.job_status_machine import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    JobStatusMachine,
)


# --- Job Status State Machine unit tests ---


class TestJobStatusMachineValidation:
    """Tests for validate_transition logic."""

    def test_valid_pending_to_processing(self):
        assert JobStatusMachine.validate_transition("pending", "processing") is True

    def test_valid_processing_to_done(self):
        assert JobStatusMachine.validate_transition("processing", "done") is True

    def test_valid_processing_to_partial(self):
        assert JobStatusMachine.validate_transition("processing", "partial") is True

    def test_valid_processing_to_failed(self):
        assert JobStatusMachine.validate_transition("processing", "failed") is True

    def test_invalid_pending_to_done(self):
        assert JobStatusMachine.validate_transition("pending", "done") is False

    def test_invalid_pending_to_failed(self):
        assert JobStatusMachine.validate_transition("pending", "failed") is False

    def test_invalid_done_to_processing(self):
        assert JobStatusMachine.validate_transition("done", "processing") is False

    def test_invalid_failed_to_processing(self):
        assert JobStatusMachine.validate_transition("failed", "processing") is False

    def test_invalid_unknown_status(self):
        assert JobStatusMachine.validate_transition("unknown", "processing") is False

    def test_valid_transitions_map_completeness(self):
        """Ensure all expected transitions are defined."""
        assert VALID_TRANSITIONS == {
            "pending": {"processing"},
            "processing": {"done", "partial", "failed"},
        }


class TestJobStatusMachineTransition:
    """Tests for the atomic transition method."""

    @pytest.mark.asyncio
    async def test_transition_job_not_found(self):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)

        with patch(
            "app.services.job_status_machine.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            with pytest.raises(InvalidTransitionError, match="not found"):
                await JobStatusMachine.transition("nonexistent-job", "processing")

    @pytest.mark.asyncio
    async def test_transition_invalid_raises_error(self):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"job_id": "job-1", "status": "pending"}
        )

        with patch(
            "app.services.job_status_machine.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            with pytest.raises(InvalidTransitionError, match="Invalid transition"):
                await JobStatusMachine.transition("job-1", "done")

    @pytest.mark.asyncio
    async def test_transition_successful(self):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"job_id": "job-1", "status": "pending"}
        )
        mock_collection.find_one_and_update = AsyncMock(
            return_value={"job_id": "job-1", "status": "processing"}
        )

        with patch(
            "app.services.job_status_machine.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            await JobStatusMachine.transition("job-1", "processing")

        # Verify find_one_and_update was called with correct filter
        call_args = mock_collection.find_one_and_update.call_args
        filter_arg = call_args[0][0]
        assert filter_arg["job_id"] == "job-1"
        assert filter_arg["status"] == "pending"

        update_arg = call_args[0][1]
        assert update_arg["$set"]["status"] == "processing"

    @pytest.mark.asyncio
    async def test_transition_sets_completed_at_for_terminal_states(self):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"job_id": "job-1", "status": "processing"}
        )
        mock_collection.find_one_and_update = AsyncMock(
            return_value={"job_id": "job-1", "status": "done"}
        )

        with patch(
            "app.services.job_status_machine.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            await JobStatusMachine.transition("job-1", "done")

        call_args = mock_collection.find_one_and_update.call_args
        update_arg = call_args[0][1]
        assert "completed_at" in update_arg["$set"]

    @pytest.mark.asyncio
    async def test_transition_sets_error_field(self):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"job_id": "job-1", "status": "processing"}
        )
        mock_collection.find_one_and_update = AsyncMock(
            return_value={"job_id": "job-1", "status": "failed"}
        )

        with patch(
            "app.services.job_status_machine.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            await JobStatusMachine.transition("job-1", "failed", error="Parse error")

        call_args = mock_collection.find_one_and_update.call_args
        update_arg = call_args[0][1]
        assert update_arg["$set"]["error"] == "Parse error"

    @pytest.mark.asyncio
    async def test_transition_race_condition_raises_error(self):
        """If another process changed the status first, find_one_and_update returns None."""
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"job_id": "job-1", "status": "pending"}
        )
        # Simulate race condition: update returns None (no document matched)
        mock_collection.find_one_and_update = AsyncMock(return_value=None)

        with patch(
            "app.services.job_status_machine.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            with pytest.raises(InvalidTransitionError, match="Atomic transition failed"):
                await JobStatusMachine.transition("job-1", "processing")


# --- Job Status Endpoint unit tests ---


class TestGetJobStatusEndpoint:
    """Tests for GET /api/ingest/{job_id}/status endpoint."""

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI

        from app.routers.ingest import router

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_job_not_found_returns_404(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/nonexistent/status",
                    headers={"X-User-Id": "user-1"},
                )

        assert response.status_code == 404
        assert response.json()["detail"] == "Job not found"

    @pytest.mark.asyncio
    async def test_unauthorized_user_returns_403(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "owner-user",
                "status": "pending",
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "other-user"},
                )

        assert response.status_code == 403
        assert response.json()["detail"] == "Not authorized to view this job"

    @pytest.mark.asyncio
    async def test_pending_status_returns_correct_message(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "user-1",
                "status": "pending",
                "completed_at": None,
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "user-1"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["message"] == "Job is queued for processing"
        assert data["completedAt"] is None

    @pytest.mark.asyncio
    async def test_processing_status_returns_correct_message(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "user-1",
                "status": "processing",
                "completed_at": None,
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "user-1"},
                )

        data = response.json()
        assert data["status"] == "processing"
        assert data["message"] == "Job is being processed"

    @pytest.mark.asyncio
    async def test_done_status_returns_correct_message_with_completed_at(self, app):
        completed_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "user-1",
                "status": "done",
                "completed_at": completed_time,
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "user-1"},
                )

        data = response.json()
        assert data["status"] == "done"
        assert data["message"] == "All processing completed successfully"
        assert data["completedAt"] == completed_time.isoformat()

    @pytest.mark.asyncio
    async def test_partial_status_returns_correct_message(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "user-1",
                "status": "partial",
                "completed_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "user-1"},
                )

        data = response.json()
        assert data["status"] == "partial"
        assert "Structured data was saved but embedding failed" in data["message"]

    @pytest.mark.asyncio
    async def test_failed_status_returns_error_field(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "user-1",
                "status": "failed",
                "error": "PDF extraction failed: corrupt file",
                "completed_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "user-1"},
                )

        data = response.json()
        assert data["status"] == "failed"
        assert data["message"] == "PDF extraction failed: corrupt file"

    @pytest.mark.asyncio
    async def test_failed_status_without_error_field_returns_default(self, app):
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "job_id": "job-1",
                "user_id": "user-1",
                "status": "failed",
                "completed_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            }
        )

        with patch(
            "app.routers.ingest.get_ingestion_jobs_collection",
            return_value=mock_collection,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/ingest/job-1/status",
                    headers={"X-User-Id": "user-1"},
                )

        data = response.json()
        assert data["status"] == "failed"
        assert data["message"] == "Processing failed"


# --- Property-Based Tests ---

from hypothesis import given, settings
from hypothesis import strategies as st


ALL_STATUSES = ["pending", "processing", "done", "partial", "failed"]


# Feature: ingestion-pipeline, Property 15: Job status valid transitions
class TestJobStatusValidTransitionsPBT:
    """Property 15: Job status valid transitions.

    For any (current_status, new_status) pair from all possible statuses,
    transition accepted iff following valid paths.
    """

    @given(
        current_status=st.sampled_from(ALL_STATUSES),
        new_status=st.sampled_from(ALL_STATUSES),
    )
    @settings(max_examples=100)
    def test_transition_validity(self, current_status: str, new_status: str):
        """**Validates: Requirements 8.2, 8.5**

        Transition accepted iff following valid paths:
        pending → processing, processing → done/partial/failed.
        All other transitions are rejected.
        """
        result = JobStatusMachine.validate_transition(current_status, new_status)

        # Define expected valid transitions
        valid_pairs = {
            ("pending", "processing"),
            ("processing", "done"),
            ("processing", "partial"),
            ("processing", "failed"),
        }

        expected = (current_status, new_status) in valid_pairs
        assert result == expected, (
            f"validate_transition('{current_status}', '{new_status}') = {result}, "
            f"expected {expected}"
        )

    @given(
        unknown_status=st.text(min_size=1, max_size=15).filter(
            lambda s: s not in ALL_STATUSES
        ),
        any_status=st.sampled_from(ALL_STATUSES),
    )
    @settings(max_examples=100)
    def test_unknown_source_always_rejects(self, unknown_status: str, any_status: str):
        """Unknown source status always rejects transitions."""
        assert JobStatusMachine.validate_transition(unknown_status, any_status) is False

    @given(
        any_status=st.sampled_from(ALL_STATUSES),
        unknown_target=st.text(min_size=1, max_size=15).filter(
            lambda s: s not in ALL_STATUSES
        ),
    )
    @settings(max_examples=100)
    def test_unknown_target_always_rejects(self, any_status: str, unknown_target: str):
        """Unknown target status always rejects transitions."""
        assert JobStatusMachine.validate_transition(any_status, unknown_target) is False
