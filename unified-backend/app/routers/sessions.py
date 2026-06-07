"""Sessions router — /api/sessions CRUD."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.config.database import sessions_col
from app.core.security import require_auth
from app.models.session import Message, SessionCreate, SessionDoc

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


class SessionUpdate(BaseModel):
    """Fields allowed in a PATCH update."""

    messages: Optional[list[Message]] = None
    mode: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None


@router.get("", response_model=list[SessionDoc])
async def list_sessions(
    limit: Optional[int] = Query(None, ge=1),
    user_id: str = Depends(require_auth),
) -> list[dict]:
    """Return all sessions for the authenticated user, newest first."""
    query = {"user_id": user_id}
    cursor = sessions_col().find(query, {"_id": 0}).sort("created_at", -1)
    if limit is not None:
        cursor = cursor.limit(limit)
    return await cursor.to_list(length=limit or 100)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionDoc)
async def create_session(
    data: SessionCreate,
    user_id: str = Depends(require_auth),
) -> dict:
    """Create a new session and return it."""
    now = datetime.now(timezone.utc).isoformat()
    doc = SessionDoc(
        session_id=str(uuid4()),
        user_id=user_id,
        title=data.title,
        mode=data.mode,
        topic=data.topic,
        status="active",
        messages=[],
        tags=[],
        summary=None,
        created_at=now,
        updated_at=now,
    )
    record = doc.model_dump()
    await sessions_col().insert_one(record)
    record.pop("_id", None)
    return record


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


@router.patch("/{session_id}", response_model=SessionDoc)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    user_id: str = Depends(require_auth),
) -> dict:
    """Update session fields (messages, mode, topic, summary)."""
    doc = await sessions_col().find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    update_data = data.model_dump(exclude_none=True)
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
