"""Ingest router for file upload and job status endpoints."""

from fastapi import APIRouter, BackgroundTasks, Body, File, Header, HTTPException, UploadFile

from app.config.database import get_ingestion_jobs_collection
from app.models.schemas import IngestionJobResponse
from app.services.file_upload_handler import FileUploadHandler, S3UploadError

router = APIRouter(prefix="/api", tags=["ingestion"])

STATUS_MESSAGES: dict[str, str] = {
    "pending": "Job is queued for processing",
    "processing": "Job is being processed",
    "done": "All processing completed successfully",
    "partial": (
        "Structured data was saved but embedding failed. "
        "Your profile and skills are up-to-date, but some narrative "
        "search context may be missing."
    ),
}


@router.post("/ingest", response_model=IngestionJobResponse, status_code=201)
async def ingest_files(
    files: list[UploadFile] = File(...),
    user_id: str = Header(..., alias="X-User-Id"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Upload files for ingestion processing.

    Validates uploaded files, stores them in S3, creates a job record,
    and enqueues extraction as a background task.

    Returns the job ID immediately for status polling.
    """
    handler = FileUploadHandler()

    # Step 1: Validate uploaded files
    errors, validated_files = await handler.handle_upload(user_id, files)
    if errors is not None:
        raise HTTPException(
            status_code=400,
            detail=[error.model_dump(exclude_none=True) for error in errors],
        )

    # Step 2: Upload to S3
    try:
        job_id, ingestion_files = handler.upload_to_s3(user_id, validated_files)
    except S3UploadError:
        raise HTTPException(
            status_code=500,
            detail="Failed to store files",
        )

    # Step 3: Create job record and enqueue extraction
    response = await handler.create_job_and_enqueue(
        job_id, user_id, ingestion_files, background_tasks
    )

    return response


@router.post("/ingest/trigger")
async def trigger_extraction(
    job_id: str = Body(..., embed=True),
    user_id: str = Header(..., alias="X-User-Id"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Trigger extraction for a job already created in MongoDB.

    Called by Next.js after it creates the job record directly (session upload flow).
    Returns immediately; extraction runs as a background task.
    """
    handler = FileUploadHandler()
    background_tasks.add_task(handler._run_extraction, job_id, user_id)
    return {"status": "ok"}


@router.get("/ingest/{job_id}/status")
async def get_job_status(
    job_id: str,
    user_id: str = Header(..., alias="X-User-Id"),
):
    """Poll the status of an ingestion job.

    Returns current status, a human-readable message, and completion time.
    Only the job owner can query its status.
    """
    collection = get_ingestion_jobs_collection()
    job = await collection.find_one({"job_id": job_id})

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    status = job["status"]

    # Determine message based on status
    if status == "failed":
        message = job.get("error") or "Processing failed"
    else:
        message = STATUS_MESSAGES.get(status, "Unknown status")

    # Format completed_at as ISO string or null
    completed_at = None
    if job.get("completed_at") is not None:
        completed_at = job["completed_at"].isoformat()

    return {
        "status": status,
        "message": message,
        "completedAt": completed_at,
    }
