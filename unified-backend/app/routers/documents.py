"""Documents router — /api/documents/ upload, status, and retry endpoints.

Provides the chat-based document upload pipeline that is fully independent
from the existing /api/ingest/ onboarding pipeline. Accepts multi-format
document uploads, creates Upload_Jobs, and returns job IDs for status polling.

This pipeline's sole output target is L1 Core Profile via PendingProfileChange.
It does NOT write to Vector DB or produce embeddings.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile

from app.auth.dependencies import require_auth
from app.config.database import document_upload_jobs_col
from app.models.document_upload import DocumentUploadJob, UploadFileRecord
from app.services.document_pipeline import process_document_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# --- Constants ---
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
    "text/plain",
    "text/markdown",
    "application/rtf",
}

MAX_FILES = 5
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Base directory for file storage
UPLOADS_BASE_DIR = Path("uploads")


@router.post("/upload", status_code=202)
async def upload_documents(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    skip_review: bool = Form(default=False),
    message: Optional[str] = Form(default=None),
    user_id: str = Depends(require_auth),
) -> dict:
    """Accept document upload, validate, store, create job, return jobId.

    Validates each file's MIME type and size. Creates an Upload_Job record
    and enqueues background processing (extraction → synthesis → proposals).

    Returns HTTP 202 with jobId on success, 400 if all files fail validation.
    """
    # 1. Batch size check — reject if more than MAX_FILES
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum batch size is {MAX_FILES} files",
        )

    # 2. Validate each file individually
    valid_files: list[UploadFile] = []
    rejected_files: list[dict] = []

    for file in files:
        # Check MIME type
        if file.content_type not in SUPPORTED_MIME_TYPES:
            rejected_files.append({
                "filename": file.filename or "unknown",
                "reason": "Unsupported file format",
            })
            continue

        # Check file size — read content to determine size
        content = await file.read()
        file_size = len(content)
        # Seek back so we can read again later when storing
        await file.seek(0)

        if file_size > MAX_FILE_SIZE_BYTES:
            rejected_files.append({
                "filename": file.filename or "unknown",
                "reason": "File exceeds 10 MB limit",
            })
            continue

        # File passes validation — store metadata for later
        file._validated_size = file_size  # type: ignore[attr-defined]
        valid_files.append(file)

    # 3. If all files fail validation, return 400
    if not valid_files:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "All files failed validation",
                "errors": rejected_files,
            },
        )

    # 4. Generate job ID and store valid files to disk
    job_id = str(uuid.uuid4())
    upload_dir = UPLOADS_BASE_DIR / user_id / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_records: list[UploadFileRecord] = []
    file_paths: list[str] = []
    mime_types: list[str] = []

    for file in valid_files:
        filename = file.filename or f"unnamed_{uuid.uuid4().hex[:8]}"
        file_path = upload_dir / filename
        content = await file.read()

        # Write file to disk
        file_path.write_bytes(content)

        file_size = getattr(file, "_validated_size", len(content))

        record = UploadFileRecord(
            filename=filename,
            mime_type=file.content_type or "application/octet-stream",
            file_path=str(file_path),
            size_bytes=file_size,
            status="pending",
        )
        file_records.append(record)
        file_paths.append(str(file_path))
        mime_types.append(file.content_type or "application/octet-stream")

    # 5. Create Upload_Job record in MongoDB
    now = datetime.now(timezone.utc)
    job = DocumentUploadJob(
        job_id=job_id,
        user_id=user_id,
        status="pending",
        files=file_records,
        skip_review=skip_review,
        message=message,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
    )

    col = document_upload_jobs_col()
    await col.insert_one(job.model_dump())

    # 6. Enqueue background processing
    background_tasks.add_task(
        process_document_upload,
        job_id=job_id,
        user_id=user_id,
        file_paths=file_paths,
        mime_types=mime_types,
        skip_review=skip_review,
    )

    logger.info(
        "Created upload job %s for user %s: %d accepted, %d rejected",
        job_id,
        user_id,
        len(valid_files),
        len(rejected_files),
    )

    # 7. Return response
    return {
        "jobId": job_id,
        "acceptedFiles": len(valid_files),
        "rejectedFiles": rejected_files,
    }


@router.get("/jobs/{job_id}/status")
async def get_job_status(
    job_id: str,
    user_id: str = Depends(require_auth),
) -> dict:
    """Return current Upload_Job status for polling.

    Includes job status, per-file statuses, proposals (when done),
    failed files, and timestamps.
    """
    col = document_upload_jobs_col()
    doc = await col.find_one({"job_id": job_id})

    if doc is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if doc["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")

    # Build per-file status list
    files = [
        {"filename": f["filename"], "status": f["status"]}
        for f in doc.get("files", [])
    ]

    # Derive failed files from files where status == "failed"
    failed_files = [
        {"filename": f["filename"], "reason": f.get("error", "Unknown error")}
        for f in doc.get("files", [])
        if f["status"] == "failed"
    ]

    # Proposals are only returned when job is done
    proposals = doc.get("proposals") if doc["status"] == "done" else None

    # Format created_at as ISO string
    created_at = doc.get("created_at")
    if created_at is not None:
        created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    else:
        created_at_str = None

    return {
        "jobId": doc["job_id"],
        "status": doc["status"],
        "files": files,
        "proposals": proposals,
        "failedFiles": failed_files,
        "proposalCount": doc.get("proposal_count", 0),
        "createdAt": created_at_str,
    }


@router.post("/jobs/{job_id}/retry-analysis", status_code=202)
async def retry_analysis(
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_auth),
) -> dict:
    """Retry LLM synthesis using preserved extracted text.

    Re-runs the L1 fact synthesis step without requiring re-upload
    or re-extraction. Only valid for jobs in 'failed' state that
    have preserved extracted_text.

    Returns HTTP 202 indicating the retry has been initiated.
    Returns 404 if job not found, 403 if not the owner,
    409 if job is not in 'failed' state, 400 if no extracted_text available.
    """
    col = document_upload_jobs_col()
    doc = await col.find_one({"job_id": job_id})

    # 1. Job must exist
    if doc is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # 2. Job must belong to the authenticated user
    if doc["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")

    # 3. Job must be in 'failed' state
    if doc["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is in '{doc['status']}' state — retry is only available for failed jobs",
        )

    # 4. Extracted text must be preserved on the job record
    extracted_text = doc.get("extracted_text")
    if not extracted_text:
        raise HTTPException(
            status_code=400,
            detail="No extracted text available for retry — extraction failed completely, re-upload required",
        )

    # 5. Reset job status to 'synthesizing'
    now = datetime.now(timezone.utc)
    await col.update_one(
        {"job_id": job_id},
        {"$set": {"status": "synthesizing", "updated_at": now}},
    )

    # 6. Kick off background task for synthesis only (skip extraction)
    skip_review = doc.get("skip_review", False)
    background_tasks.add_task(
        _run_retry_synthesis,
        job_id=job_id,
        user_id=user_id,
        extracted_text=extracted_text,
        skip_review=skip_review,
    )

    logger.info("Retry analysis initiated for job %s by user %s", job_id, user_id)

    return {"jobId": job_id, "status": "synthesizing", "message": "Retry analysis initiated"}


async def _run_retry_synthesis(
    job_id: str,
    user_id: str,
    extracted_text: str,
    skip_review: bool,
) -> None:
    """Background task: re-run LLM synthesis using preserved extracted text.

    This skips the extraction step entirely and goes directly to synthesis.
    On success, updates the job to 'done' with proposals.
    On failure, updates the job back to 'failed' with error details.

    Args:
        job_id: The Upload_Job ID.
        user_id: The authenticated user's ID.
        extracted_text: The preserved extracted text from the job record.
        skip_review: Whether to skip review and apply changes directly.
    """
    from app.services.l1_fact_synthesizer import synthesize_l1_facts

    col = document_upload_jobs_col()

    try:
        # Run synthesis
        synthesis_result = await synthesize_l1_facts(
            extracted_text=extracted_text,
            user_id=user_id,
            job_id=job_id,
        )

        now = datetime.now(timezone.utc)

        if not synthesis_result.success:
            # Synthesis failed again — mark job as failed
            await col.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "failed",
                    "proposals": None,
                    "proposal_count": 0,
                    "updated_at": now,
                }},
            )
            logger.error(
                "Retry synthesis failed for job %s: %s", job_id, synthesis_result.error
            )
            return

        # Synthesis succeeded — update job to 'done' with proposals
        proposals = synthesis_result.proposals or []
        await col.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "done",
                "proposals": proposals,
                "proposal_count": len(proposals),
                "updated_at": now,
            }},
        )

        logger.info(
            "Retry synthesis completed for job %s: %d proposals generated",
            job_id,
            len(proposals),
        )

    except Exception as e:
        # Catch-all: ensure the job doesn't stay in a non-terminal state
        logger.error(
            "Unhandled error in retry synthesis for job %s: %s", job_id, e, exc_info=True
        )
        try:
            await col.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "failed",
                    "proposals": None,
                    "proposal_count": 0,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
        except Exception as update_err:
            logger.error(
                "Failed to update job %s status to failed during retry: %s",
                job_id,
                update_err,
            )
