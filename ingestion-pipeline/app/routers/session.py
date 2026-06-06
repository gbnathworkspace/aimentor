"""Session router: endpoint for ending a session via CheckpointService."""

from __future__ import annotations

from fastapi import APIRouter, Body, Header

from app.services.checkpoint_service import CheckpointService

router = APIRouter(tags=["session"])


@router.post("/session/end")
async def end_session(
    session_id: str = Body(..., embed=True),
    user_id: str = Header(..., alias="X-User-Id"),
):
    """End a session: invoke LLM summarization and persist results.

    Returns 200 even if the session becomes orphaned — the client
    should not retry because the checkpoint mechanism handles recovery.
    """
    service = CheckpointService()
    await service.end_session(session_id, user_id)
    return {"status": "ok"}
