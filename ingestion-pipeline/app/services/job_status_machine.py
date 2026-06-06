"""Job status state machine with valid transition logic and atomic updates."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.database import get_ingestion_jobs_collection


class InvalidTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""

    pass


# Valid transitions: from_status -> set of valid to_statuses
VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"processing"},
    "processing": {"done", "partial", "failed"},
}


class JobStatusMachine:
    """Manages job status transitions with validation and atomic updates."""

    @staticmethod
    def validate_transition(current_status: str, new_status: str) -> bool:
        """Return True if the transition is valid, False otherwise."""
        allowed = VALID_TRANSITIONS.get(current_status, set())
        return new_status in allowed

    @staticmethod
    async def transition(
        job_id: str, new_status: str, error: str | None = None
    ) -> None:
        """Atomically transition a job to a new status.

        Uses findOneAndUpdate with current_status filter to prevent race conditions.
        Raises InvalidTransitionError if transition is not valid or if the atomic
        update matches 0 documents (status already changed by another process).
        """
        collection = get_ingestion_jobs_collection()

        # Look up current status
        job = await collection.find_one({"job_id": job_id})
        if job is None:
            raise InvalidTransitionError(
                f"Job '{job_id}' not found"
            )

        current_status = job["status"]

        # Validate the transition
        if not JobStatusMachine.validate_transition(current_status, new_status):
            raise InvalidTransitionError(
                f"Invalid transition from '{current_status}' to '{new_status}'"
            )

        # Build the update document
        now = datetime.now(UTC)
        update_fields: dict = {
            "status": new_status,
            "updated_at": now,
        }

        if error is not None:
            update_fields["error"] = error

        # Set completed_at for terminal states
        if new_status in {"done", "partial", "failed"}:
            update_fields["completed_at"] = now

        # Atomic update with optimistic locking on current status
        result = await collection.find_one_and_update(
            {"job_id": job_id, "status": current_status},
            {"$set": update_fields},
        )

        if result is None:
            raise InvalidTransitionError(
                f"Atomic transition failed for job '{job_id}': "
                f"status may have already changed from '{current_status}'"
            )
