"""MessageStore: atomic message persistence for session documents.

Provides three core operations:
- append_messages: atomic $push with $each (only for active sessions)
- checkpoint: full $set replacement of messages array (idempotent)
- get_messages: retrieve messages sorted by timestamp ascending

Retry policy: 1 retry after 1s delay using idempotent write
(match on session_id + message timestamp to prevent duplicates).
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.config.database import sessions_col
from app.models.session import Message, SessionStatus

logger = logging.getLogger(__name__)


class SessionNotActiveError(Exception):
    """Raised when an operation targets a session that is not active."""

    def __init__(self, session_id: str, current_status: str):
        self.session_id = session_id
        self.current_status = current_status
        super().__init__(
            f"Session '{session_id}' is not accepting messages "
            f"(current status: '{current_status}')"
        )


class MessageStore:
    """Handles incremental message persistence with atomic MongoDB operations."""

    async def append_messages(
        self, session_id: str, messages: list[Message]
    ) -> None:
        """Atomically append messages to a session document.

        Uses $push with $each for atomic append. Only succeeds if the
        session status is 'active'. Retries once after 1s on failure
        using an idempotent write to prevent duplicates.

        Args:
            session_id: The session to append to.
            messages: List of Message objects to append.

        Raises:
            SessionNotActiveError: If the session status is not 'active'.
            RuntimeError: If the append fails after retry.
        """
        # First, verify the session exists and is active
        session = await sessions_col().find_one(
            {"session_id": session_id}, {"status": 1}
        )

        if session is None:
            raise SessionNotActiveError(session_id, "not_found")

        if session.get("status") != SessionStatus.active.value:
            raise SessionNotActiveError(
                session_id, session.get("status", "unknown")
            )

        now = datetime.now(timezone.utc).isoformat()
        message_dicts = [msg.model_dump() for msg in messages]

        # Attempt atomic $push
        try:
            result = await self._do_append(session_id, message_dicts, now)
            if result.modified_count == 0:
                # Session may have transitioned between check and write
                raise RuntimeError("Append matched no active session")
        except Exception as first_err:
            logger.warning(
                "First append attempt failed for session %s: %s",
                session_id,
                str(first_err),
            )
            # Retry once after 1s with idempotent write
            await asyncio.sleep(1)
            try:
                await self._do_idempotent_append(
                    session_id, message_dicts, now
                )
            except Exception as retry_err:
                logger.error(
                    "Retry append failed for session %s: %s",
                    session_id,
                    str(retry_err),
                )
                raise RuntimeError(
                    f"Failed to append messages to session '{session_id}' "
                    f"after retry: {retry_err}"
                ) from retry_err

    async def checkpoint(
        self, session_id: str, messages: list[Message]
    ) -> None:
        """Replace the full messages array for a session (idempotent).

        Uses $set for full array replacement. This is safe to call
        multiple times with the same data — last write wins.

        Args:
            session_id: The session to checkpoint.
            messages: Complete list of messages to set.
        """
        now = datetime.now(timezone.utc).isoformat()
        message_dicts = [msg.model_dump() for msg in messages]

        await sessions_col().update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "messages": message_dicts,
                    "updated_at": now,
                }
            },
        )

    async def get_messages(self, session_id: str) -> list[Message]:
        """Retrieve messages for a session sorted by timestamp ascending.

        Args:
            session_id: The session to retrieve messages from.

        Returns:
            List of Message objects in chronological order.
        """
        session = await sessions_col().find_one(
            {"session_id": session_id}, {"messages": 1}
        )

        if session is None:
            return []

        raw_messages = session.get("messages", [])

        # Parse into Message objects and sort by timestamp
        parsed = []
        for msg_data in raw_messages:
            try:
                parsed.append(Message(**msg_data))
            except Exception as e:
                logger.warning(
                    "Skipping malformed message in session %s: %s",
                    session_id,
                    str(e),
                )

        # Sort by timestamp ascending (None timestamps sort first)
        parsed.sort(key=lambda m: m.timestamp or "")

        return parsed

    # ──────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────

    async def _do_append(
        self, session_id: str, message_dicts: list[dict], updated_at: str
    ):
        """Perform atomic $push append, filtering for active status."""
        return await sessions_col().update_one(
            {"session_id": session_id, "status": SessionStatus.active.value},
            {
                "$push": {"messages": {"$each": message_dicts}},
                "$set": {"updated_at": updated_at},
            },
        )

    async def _do_idempotent_append(
        self, session_id: str, message_dicts: list[dict], updated_at: str
    ) -> None:
        """Idempotent retry: only append messages not already present.

        Matches on session_id and checks message timestamps to avoid
        duplicating messages that may have been written on the first attempt.
        """
        for msg in message_dicts:
            timestamp = msg.get("timestamp")
            role = msg.get("role")

            if timestamp and role:
                # Only append if no message with this timestamp+role exists
                result = await sessions_col().update_one(
                    {
                        "session_id": session_id,
                        "status": SessionStatus.active.value,
                        "messages": {
                            "$not": {
                                "$elemMatch": {
                                    "timestamp": timestamp,
                                    "role": role,
                                }
                            }
                        },
                    },
                    {
                        "$push": {"messages": msg},
                        "$set": {"updated_at": updated_at},
                    },
                )
                if result.modified_count == 0:
                    # Either already exists (idempotent success) or session
                    # is no longer active
                    session = await sessions_col().find_one(
                        {"session_id": session_id}, {"status": 1}
                    )
                    if (
                        session
                        and session.get("status")
                        != SessionStatus.active.value
                    ):
                        raise SessionNotActiveError(
                            session_id,
                            session.get("status", "unknown"),
                        )
                    # Otherwise, message already exists — idempotent success
            else:
                # No timestamp for dedup — just push (best effort)
                await sessions_col().update_one(
                    {
                        "session_id": session_id,
                        "status": SessionStatus.active.value,
                    },
                    {
                        "$push": {"messages": msg},
                        "$set": {"updated_at": updated_at},
                    },
                )
