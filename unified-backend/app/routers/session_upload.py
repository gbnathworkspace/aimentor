"""Session file-upload router — restores the chat file-upload feature.

Contract expected by the SPA's useFileUpload hook:
  * POST /api/session/{session_id}/upload  (multipart: file [+ accompanyingMessage])
        -> 202 { jobId }
  * GET  /api/session/{session_id}/upload/{job_id}/status
        -> { status, extractionReady, summary }

Extracted text is stored as an ImmediateContext block for the session, which
mentor.py injects into the system prompt (token-budget trimmed).
"""

import csv
import io
import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader

from app.config.database import immediate_contexts_col, ingestion_jobs_col
from app.auth.dependencies import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session", tags=["Session Upload"])


def _extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded file (PDF / CSV / text)."""
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if name.endswith(".csv"):
            text = data.decode("utf-8", errors="replace")
            rows: list[str] = []
            for row in csv.DictReader(io.StringIO(text)):
                parts = [f"{k}: {v}" for k, v in row.items() if v]
                if parts:
                    rows.append(" | ".join(parts))
            return "\n".join(rows)
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("Text extraction failed for %s: %s", filename, e)
        return ""


async def _process_upload(
    job_id: str, session_id: str, user_id: str, filename: str, data: bytes
) -> None:
    """Background task: extract text, store as ImmediateContext, mark job ready."""
    text = _extract_text(filename, data)
    try:
        if text.strip():
            await immediate_contexts_col().update_one(
                {"session_id": session_id, "user_id": user_id},
                {"$push": {"blocks": {"filename": filename or "file", "content": text}}},
                upsert=True,
            )
            await ingestion_jobs_col().update_one(
                {"job_id": job_id},
                {"$set": {
                    # "done" is a terminal status the client recognizes (stops polling);
                    # extraction_ready drives the "file is ready" UI message.
                    "status": "done",
                    "extraction_ready": True,
                    "summary": f"{filename or 'File'} is ready ({len(text)} characters extracted).",
                }},
            )
        else:
            await ingestion_jobs_col().update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "failed",
                    "extraction_ready": False,
                    "summary": "No readable text could be extracted from this file.",
                }},
            )
    except Exception as e:
        logger.warning("Upload processing failed for job %s: %s", job_id, e)
        await ingestion_jobs_col().update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "extraction_ready": False, "summary": str(e)[:120]}},
        )


@router.post("/{session_id}/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_session_file(
    session_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    accompanyingMessage: Optional[str] = Form(None),
    user_id: str = Depends(require_auth),
) -> dict:
    """Accept a file for a session, enqueue extraction, return a job id (202)."""
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "Empty file"}
        )

    job_id = str(uuid4())
    await ingestion_jobs_col().insert_one({
        "job_id": job_id,
        "user_id": user_id,
        "session_id": session_id,
        "filename": file.filename or "file",
        "status": "processing",
        "extraction_ready": False,
        "summary": None,
    })

    background_tasks.add_task(
        _process_upload, job_id, session_id, user_id, file.filename or "file", data
    )

    return {"jobId": job_id}


@router.get("/{session_id}/upload/{job_id}/status")
async def upload_status(
    session_id: str,
    job_id: str,
    user_id: str = Depends(require_auth),
) -> dict:
    """Return processing status for an upload job."""
    job = await ingestion_jobs_col().find_one({"job_id": job_id}, {"_id": 0})
    if not job or job.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"error": "Job not found"}
        )
    return {
        "status": job.get("status", "processing"),
        "extractionReady": bool(job.get("extraction_ready")),
        "summary": job.get("summary"),
    }
