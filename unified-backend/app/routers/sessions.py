"""Sessions router — /api/sessions CRUD + persistence endpoints."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.config.database import sessions_col
from app.core.security import require_auth
from app.models.session import Message, SessionCreate, SessionDoc, SessionEndResult, SessionStatus
from app.services.message_store import MessageStore, SessionNotActiveError
from app.services.session_manager import SessionManager
from app.services.session_save_handler import SessionSaveHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])

# Service singletons
_session_manager = SessionManager()
_message_store = MessageStore()
_session_save_handler = SessionSaveHandler()


class SessionUpdate(BaseModel):
    """Fields allowed in a PATCH update."""

    title: Optional[str] = None
    messages: Optional[list[Message]] = None
    mode: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None


class MessagesRequest(BaseModel):
    """Request body for appending messages."""

    messages: list[Message]


class CheckpointRequest(BaseModel):
    """Request body for checkpointing messages."""

    messages: list[Message]


class RecoverRequest(BaseModel):
    """Request body for recovering orphaned messages."""

    messages: list[Message]


@router.get("", response_model=list[SessionDoc])
async def list_sessions(
    limit: Optional[int] = Query(None, ge=1),
    user_id: str = Depends(require_auth),
) -> list[dict]:
    """Return the user's chat sessions, most-recently-active first.

    Filters to live chat sessions (those with a `messages` array), excluding
    episodic-summary documents that also live in this collection.
    """
    query = {"user_id": user_id, "messages": {"$exists": True}}
    cursor = sessions_col().find(query, {"_id": 0}).sort("updated_at", -1)
    if limit is not None:
        cursor = cursor.limit(limit)
    return await cursor.to_list(length=limit or 100)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionDoc)
async def create_session(
    data: SessionCreate,
    user_id: str = Depends(require_auth),
) -> dict:
    """Create a new session using SessionManager and return it."""
    session_doc = await _session_manager.create_session(
        user_id=user_id,
        mode=data.mode,
        topic=data.topic,
    )
    # Return as dict for response serialization, matching SessionDoc shape
    result = session_doc.model_dump(by_alias=False)
    # Apply title from request if provided (SessionManager defaults to "Untitled session")
    if data.title and data.title != "Untitled session":
        result["title"] = data.title
        await sessions_col().update_one(
            {"session_id": result["session_id"]},
            {"$set": {"title": data.title}},
        )
    return result


@router.get("/{session_id}", response_model=SessionDoc)
async def get_session(
    session_id: str,
    user_id: str = Depends(require_auth),
) -> dict:
    """Return a single session including messages."""
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return doc


@router.patch("/{session_id}", response_model=None)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    user_id: str = Depends(require_auth),
):
    """Update session fields or trigger lifecycle transitions.

    When `status: "ending"` is included, triggers the full session-end pipeline:
    1. Transition session to 'ending'
    2. Run SessionSaveHandler.process_end (LLM summary + skill update)
    3. Session transitions to 'ended' (handled by SessionSaveHandler)
    4. Return SessionEndResult

    For regular field updates (title, messages, mode, topic, summary),
    the existing behavior is preserved.
    """
    # Check session exists and belongs to user
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Handle session-end lifecycle transition
    if data.status == "ending":
        # Transition to 'ending' via state machine
        try:
            await _session_manager.transition_status(
                session_id, user_id, SessionStatus.ending
            )
        except HTTPException as e:
            # If session is already ended (e.g. ended in a prior request, or by timeout sweep),
            # return the saved summary gracefully instead of surfacing a 409 to the client.
            if e.status_code == 409:
                current = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
                if current and current.get("status") == SessionStatus.ended.value:
                    logger.info(
                        "Session %s already ended — returning cached result for idempotent end request",
                        session_id,
                    )
                    return {
                        "session_id": session_id,
                        "title": current.get("title", "Untitled session"),
                        "summary": current.get("summary", "Session saved."),
                        "skill_update": current.get("skill_update"),
                        "status": "ended",
                    }
            logger.error(
                "Session transition failed session=%s user=%s status=%d detail=%s",
                session_id, user_id, e.status_code, e.detail,
            )
            raise

        # Run end-of-session processing
        topic = doc.get("topic") or ""
        mode = doc.get("mode") or "topic"

        try:
            result = await _session_save_handler.process_end(
                session_id=session_id,
                user_id=user_id,
                topic=topic,
                mode=mode,
            )
            return result.model_dump(by_alias=False)
        except Exception as e:
            # Requirement 1.5: even if processing fails, session must reach 'ended'
            logger.error(
                "Session end processing failed for %s: %s", session_id, str(e)
            )
            # Force transition to ended
            now = datetime.now(timezone.utc).isoformat()
            await sessions_col().update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "status": SessionStatus.ended.value,
                        "ended_at": now,
                        "updated_at": now,
                        "failure_reason": f"End processing failed: {str(e)}",
                    }
                },
            )
            # Return a minimal result so the client knows the session ended
            return {
                "session_id": session_id,
                "title": doc.get("title", "Untitled session"),
                "summary": "Session ended before processing could complete.",
                "skill_update": None,
                "status": "ended",
            }

    # Regular field update (non-lifecycle)
    update_data = data.model_dump(exclude_none=True, exclude={"status"})
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Convert Message models to dicts for storage
    if "messages" in update_data:
        update_data["messages"] = [
            m if isinstance(m, dict) else m for m in update_data["messages"]
        ]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await sessions_col().update_one(
        {"session_id": session_id},
        {"$set": update_data},
    )

    updated = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    return updated


@router.post("/{session_id}/messages", status_code=status.HTTP_200_OK)
async def append_messages(
    session_id: str,
    data: MessagesRequest,
    user_id: str = Depends(require_auth),
) -> dict:
    """Append messages to a session. Only works for active sessions.

    Returns 409 if the session is not in 'active' status.
    """
    # Verify ownership
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if not data.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="messages field is required and cannot be empty",
        )

    try:
        await _message_store.append_messages(session_id, data.messages)
    except SessionNotActiveError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return {"ok": True}


@router.post("/{session_id}/checkpoint", status_code=status.HTTP_200_OK)
async def checkpoint_messages(
    session_id: str,
    data: CheckpointRequest,
    user_id: str = Depends(require_auth),
) -> dict:
    """Checkpoint (full replacement) of the messages array for a session.

    This is an idempotent operation — safe to call multiple times.
    """
    # Verify ownership
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if not data.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="messages field is required and cannot be empty",
        )

    await _message_store.checkpoint(session_id, data.messages)
    return {"ok": True}


@router.post("/{session_id}/recover", status_code=status.HTTP_200_OK)
async def recover_messages(
    session_id: str,
    data: RecoverRequest,
    user_id: str = Depends(require_auth),
) -> dict:
    """Recover orphaned messages from localStorage.

    Deduplicates by (timestamp, role) and appends missing messages
    in chronological order. If the recovered session has not already ended,
    triggers end-of-session processing (summary + skill update + embedding)
    so the session is fully closed before the client clears localStorage.

    Requirements: 3.5, 3.6, 3.7
    """
    # Verify ownership
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if not data.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="messages field is required and cannot be empty",
        )

    await _session_manager.recover_orphaned_messages(
        user_id=user_id,
        session_id=session_id,
        messages=data.messages,
    )

    # After recovery, trigger end-of-session processing if not already ended (Req 3.6)
    end_processing_triggered = False
    current_status = doc.get("status", "")

    if current_status != SessionStatus.ended.value:
        topic = doc.get("topic") or ""
        mode = doc.get("mode") or "topic"

        try:
            # Transition to 'ending' if currently 'active'
            if current_status == SessionStatus.active.value:
                await _session_manager.transition_status(
                    session_id, user_id, SessionStatus.ending
                )

            # Run end-of-session processing (summary + skill update + embedding)
            await _session_save_handler.process_end(
                session_id=session_id,
                user_id=user_id,
                topic=topic,
                mode=mode,
            )
            end_processing_triggered = True
        except Exception as e:
            logger.error(
                "End-of-session processing failed during recovery for %s: %s",
                session_id,
                str(e),
            )
            # Force session to ended state so it doesn't stay stuck
            now = datetime.now(timezone.utc).isoformat()
            await sessions_col().update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "status": SessionStatus.ended.value,
                        "ended_at": now,
                        "updated_at": now,
                        "failure_reason": f"Recovery end-processing failed: {str(e)}",
                    }
                },
            )
            end_processing_triggered = True  # Still counts — session is ended

    return {"ok": True, "end_processing_triggered": end_processing_triggered}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Depends(require_auth),
) -> dict:
    """Delete a session. 404 if missing, 403 if not owned by the user."""
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await sessions_col().delete_one({"session_id": session_id})
    return {"ok": True}
