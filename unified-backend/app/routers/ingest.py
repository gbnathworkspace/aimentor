"""Ingestion router — /api/ingest upload + status + trigger."""

import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config.database import ingestion_jobs_col
from app.core.security import require_auth
from app.models.ingestion import IngestionJobResponse
from app.services.extraction import process_extraction
from app.services.file_upload import store_file, validate_files

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["Ingestion"])


class TriggerRequest(BaseModel):
    """Request body for POST /api/ingest/trigger."""

    job_id: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_files(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_auth),
) -> dict:
    """Upload files, validate, store, create job, and enqueue extraction.

    Accepts multipart form upload with one or more files.
    Validates file types and sizes. If all files are invalid, returns 400.
    For valid files, stores them, creates a job record, and enqueues
    background extraction processing.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    valid_files, errors = await validate_files(files)

    # If all files are invalid, return 400 with errors
    if not valid_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "All files failed validation", "errors": errors},
        )

    # Generate job ID and store valid files
    job_id = str(uuid4())
    file_paths: list[str] = []

    try:
        for file in valid_files:
            path = await store_file(file, user_id, job_id)
            file_paths.append(path)
    except Exception:
        logger.exception("File storage failed for job=%s user=%s", job_id, user_id)
        raise

    # Create job record in MongoDB
    job_doc = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "processing",
        "files": [f.filename or "unknown" for f in valid_files],
        "file_paths": file_paths,
        "errors": errors if errors else None,
    }
    await ingestion_jobs_col().insert_one(job_doc)

    # Enqueue background extraction
    background_tasks.add_task(process_extraction, job_id, user_id, file_paths)

    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Files uploaded successfully. Extraction in progress.",
    }


@router.get("/{job_id}/status", response_model=IngestionJobResponse)
async def get_job_status(
    job_id: str,
    user_id: str = Depends(require_auth),
) -> IngestionJobResponse:
    """Return the current status of an ingestion job.

    Enforces job ownership — returns 403 if the job belongs to another user.
    Returns 404 if the job does not exist.
    """
    doc = await ingestion_jobs_col().find_one({"job_id": job_id}, {"_id": 0})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if doc.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    return IngestionJobResponse(
        job_id=doc["job_id"],
        status=doc["status"],
        message=_status_message(doc["status"]),
        completed_at=doc.get("completed_at"),
    )


@router.post("/trigger")
async def trigger_extraction(
    data: TriggerRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_auth),
) -> dict:
    """Re-trigger extraction for an existing job.

    Looks up the job, verifies ownership, and enqueues extraction
    as a background task.
    """
    doc = await ingestion_jobs_col().find_one({"job_id": data.job_id}, {"_id": 0})

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if doc.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    # Get file paths from the job record
    file_paths = doc.get("file_paths", [])
    if not file_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file paths found for this job",
        )

    # Update job status to processing
    await ingestion_jobs_col().update_one(
        {"job_id": data.job_id},
        {"$set": {"status": "processing"}},
    )

    # Enqueue background extraction
    background_tasks.add_task(process_extraction, data.job_id, user_id, file_paths)

    return {
        "job_id": data.job_id,
        "status": "processing",
    }


def _status_message(job_status: str) -> str:
    """Return a human-readable message for a given job status."""
    messages = {
        "processing": "Extraction in progress.",
        "completed": "Extraction completed successfully.",
        "failed": "Extraction failed. Check job details for errors.",
    }
    return messages.get(job_status, f"Job status: {job_status}")
