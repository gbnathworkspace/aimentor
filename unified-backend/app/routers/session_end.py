"""Session End router — POST /api/session/end.

Delegates to the session_end service for LLM summarization,
episodic memory persistence, and skill graph updates.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.security import require_auth
from app.models.session import Message
from app.services.session_end import process_session_end

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session", tags=["Session End"])


class SessionEndRequest(BaseModel):
    """Request body for ending a session."""

    topic: str
    messages: list[Message]


class SessionEndResponse(BaseModel):
    """Response from the session end processor."""

    session_id: str
    title: str
    summary: str
    skill_update: dict


@router.post("/end", response_model=SessionEndResponse)
async def end_session(
    data: SessionEndRequest,
    user_id: str = Depends(require_auth),
) -> SessionEndResponse:
    """End a session: summarize via LLM, persist episodic memory, update skills.

    Delegates to session_end.process_session_end which:
    - Generates a structured summary via Anthropic tool_use
    - Persists the summary as an L3 episodic memory entry with embedding
    - Upserts the L2 skill graph node if skill_update is produced

    Returns session_id, title, summary, and skill_update.
    """
    try:
        # Convert Message models to dicts for the service layer
        messages_dicts = [m.model_dump() for m in data.messages]
        result = await process_session_end(user_id, data.topic, messages_dicts)
        return SessionEndResponse(**result)
    except Exception as e:
        logger.exception("Session end processing failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session end processing failed",
        )
