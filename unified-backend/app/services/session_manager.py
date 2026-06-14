"""Session lifecycle manager with state machine enforcement.

Handles session creation, status transitions, stale session cleanup,
orphaned message recovery, and timeout sweep for stuck sessions.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.config.database import sessions_col
from app.models.session import Message, SessionDocument, SessionStatus


# Valid state machine transitions: active → ending → ended
_VALID_TRANSITIONS: dict[SessionStatus, SessionStatus] = {
    SessionStatus.active: SessionStatus.ending,
    SessionStatus.ending: SessionStatus.ended,
}


class SessionManager:
    """Manages session lifecycle state transitions and persistence."""

    async def create_session(
        self, user_id: str, mode: str, topic: str | None = None
    ) -> SessionDocument:
        """Create a new active session.

        Cleans up any stale active/ending sessions for the user first,
        then inserts a new session document with status=active.

        Args:
            user_id: The authenticated user's ID.
            mode: Session mode (topic, planning, doubt, evaluation).
            topic: Optional session topic.

        Returns:
            The newly created SessionDocument.

        Raises:
            HTTPException: 400 if user_id is missing.
        """
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        # Force-end any existing active/ending sessions for this user
        await self.cleanup_stale_sessions(user_id)

        now = datetime.utcnow().isoformat()
        session_id = str(uuid.uuid4())

        doc = SessionDocument(
            session_id=session_id,
            user_id=user_id,
            title="Untitled session",
            mode=mode,
            topic=topic,
            topic_category=None,
            status=SessionStatus.active,
            messages=[],
            summary=None,
            skill_update=None,
            tags=[],
            created_at=now,
            updated_at=now,
            ended_at=None,
            failure_reason=None,
        )

        await sessions_col().insert_one(doc.model_dump(by_alias=False))
        return doc

    async def transition_status(
        self, session_id: str, user_id: str, new_status: SessionStatus
    ) -> SessionDocument:
        """Validate and apply a status transition.

        Only allows active→ending and ending→ended. All other transitions
        are rejected with HTTP 409.

        Args:
            session_id: The session to transition.
            user_id: The owning user's ID.
            new_status: The desired target status.

        Returns:
            The updated SessionDocument.

        Raises:
            HTTPException: 404 if session not found.
            HTTPException: 409 if the transition is invalid.
        """
        session = await sessions_col().find_one(
            {"session_id": session_id, "user_id": user_id}
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        current_status = SessionStatus(session["status"])
        allowed_next = _VALID_TRANSITIONS.get(current_status)

        if allowed_next != new_status:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Invalid transition: cannot move from "
                    f"'{current_status.value}' to '{new_status.value}'"
                ),
            )

        now = datetime.utcnow().isoformat()
        update_fields: dict = {"status": new_status.value, "updated_at": now}

        if new_status == SessionStatus.ended:
            update_fields["ended_at"] = now

        result = await sessions_col().find_one_and_update(
            {"session_id": session_id, "user_id": user_id},
            {"$set": update_fields},
            return_document=True,
        )

        return SessionDocument(**result)

    async def cleanup_stale_sessions(self, user_id: str) -> int:
        """Force-end all active/ending sessions for a user.

        Sets status to 'ended' with a failure_reason indicating forced cleanup.

        Args:
            user_id: The user whose stale sessions should be cleaned up.

        Returns:
            The number of sessions that were force-ended.
        """
        now = datetime.utcnow().isoformat()

        result = await sessions_col().update_many(
            {
                "user_id": user_id,
                "status": {"$in": [SessionStatus.active.value, SessionStatus.ending.value]},
            },
            {
                "$set": {
                    "status": SessionStatus.ended.value,
                    "updated_at": now,
                    "ended_at": now,
                    "failure_reason": "Forced cleanup: new session created",
                }
            },
        )

        return result.modified_count

    async def recover_orphaned_messages(
        self, user_id: str, session_id: str, messages: list[Message]
    ) -> None:
        """Deduplicate and append recovered localStorage messages to a session.

        Messages are deduplicated by (timestamp, role). Only messages not
        already present in the session document are appended, in chronological
        order.

        Args:
            user_id: The owning user's ID.
            session_id: The session to recover messages into.
            messages: The list of messages recovered from localStorage.

        Raises:
            HTTPException: 404 if session not found.
        """
        session = await sessions_col().find_one(
            {"session_id": session_id, "user_id": user_id}
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Build a set of existing (timestamp, role) keys for deduplication
        existing_keys: set[tuple[str | None, str]] = set()
        for msg in session.get("messages", []):
            existing_keys.add((msg.get("timestamp"), msg["role"]))

        # Filter to only messages not already in the session
        new_messages = []
        for msg in messages:
            key = (msg.timestamp, msg.role)
            if key not in existing_keys:
                new_messages.append(msg.model_dump())
                existing_keys.add(key)

        if not new_messages:
            return

        # Sort by timestamp before appending
        new_messages.sort(key=lambda m: m.get("timestamp") or "")

        now = datetime.utcnow().isoformat()
        await sessions_col().update_one(
            {"session_id": session_id, "user_id": user_id},
            {
                "$push": {"messages": {"$each": new_messages}},
                "$set": {"updated_at": now},
            },
        )

    async def timeout_sweep(self) -> int:
        """Transition stuck 'ending' sessions to 'ended' after 60 seconds.

        Queries sessions with status='ending' and updated_at older than
        60 seconds, then transitions them to 'ended' with a timeout
        failure_reason. Uses the { status: 1, updated_at: 1 } compound index.

        Returns:
            The number of sessions that were timed out.
        """
        now = datetime.utcnow()
        cutoff = (now - timedelta(seconds=60)).isoformat()

        result = await sessions_col().update_many(
            {
                "status": SessionStatus.ending.value,
                "updated_at": {"$lt": cutoff},
            },
            {
                "$set": {
                    "status": SessionStatus.ended.value,
                    "updated_at": now.isoformat(),
                    "ended_at": now.isoformat(),
                    "failure_reason": "timeout",
                }
            },
        )

        return result.modified_count
