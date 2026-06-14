"""MongoDB index definitions for the sessions collection.

Ensures compound indexes required by the session persistence pipeline
are created on application startup.
"""

from app.config.database import sessions_col


async def ensure_indexes() -> None:
    """Create compound indexes on the sessions collection for efficient queries.

    Indexes:
      - { user_id: 1, status: 1 }  — used by cleanup_stale_sessions to find
        active/ending sessions for a specific user.
      - { status: 1, updated_at: 1 } — used by the timeout sweep to find
        sessions stuck in 'ending' state for longer than 60 seconds.
    """
    col = sessions_col()

    # Compound index for stale session cleanup (SessionManager.cleanup_stale_sessions)
    await col.create_index(
        [("user_id", 1), ("status", 1)],
        name="idx_user_id_status",
    )

    # Compound index for timeout sweep (ending > 60s detection)
    await col.create_index(
        [("status", 1), ("updated_at", 1)],
        name="idx_status_updated_at",
    )
