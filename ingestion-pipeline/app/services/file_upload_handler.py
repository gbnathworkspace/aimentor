"""File upload handler with validation for the ingestion pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from botocore.exceptions import ClientError
from fastapi import UploadFile
from fastapi import BackgroundTasks

import logging

from app.config.database import get_ingestion_jobs_collection, get_s3_client
from app.config.settings import get_settings
from app.models.schemas import (
    FileValidationError,
    IngestionFile,
    IngestionJobResponse,
    IngestionStatus,
    JobRecord,
)

logger = logging.getLogger(__name__)

# Constants
MAX_FILES = 2
MAX_FILE_SIZE = 10_485_760  # 10 MB
ALLOWED_MIME_TYPES = {"application/pdf", "text/csv"}


class S3UploadError(Exception):
    """Raised when an S3 upload operation fails."""

    pass


def construct_s3_key(user_id: str, job_id: str, filename: str) -> str:
    """Construct the S3 object key for an uploaded file.

    Args:
        user_id: The ID of the user uploading the file.
        job_id: The UUID job identifier.
        filename: The original filename.

    Returns:
        The S3 key in format: uploads/{user_id}/{job_id}/{filename}
    """
    return f"uploads/{user_id}/{job_id}/{filename}"


class FileUploadHandler:
    """Handles file upload validation, S3 storage, and job creation."""

    async def handle_upload(
        self, user_id: str, files: list[UploadFile]
    ) -> tuple[list[FileValidationError] | None, list[tuple[bytes, str, str]] | None]:
        """Validate uploaded files and return validated file data.

        Args:
            user_id: The ID of the user uploading files.
            files: List of uploaded files from the request.

        Returns:
            A tuple of (errors, validated_files).
            - If validation fails: (list of errors, None)
            - If validation passes: (None, list of (file_bytes, filename, content_type))
        """
        errors: list[FileValidationError] = []

        # Validate file count
        if len(files) > MAX_FILES:
            errors.append(
                FileValidationError(
                    field="files",
                    message=f"Too many files. Maximum allowed is {MAX_FILES}.",
                )
            )
            return errors, None

        validated_files: list[tuple[bytes, str, str]] = []

        for file in files:
            # Validate MIME type
            if file.content_type not in ALLOWED_MIME_TYPES:
                errors.append(
                    FileValidationError(
                        field="file",
                        message=f"Unsupported file type: {file.content_type}. Allowed types: application/pdf, text/csv.",
                        supported_types=sorted(ALLOWED_MIME_TYPES),
                    )
                )
                continue

            # Read file bytes to determine actual size
            file_bytes = await file.read()
            size = len(file_bytes)

            # Validate size
            if size <= 0 or size > MAX_FILE_SIZE:
                errors.append(
                    FileValidationError(
                        field="file",
                        message=f"File size {size} bytes is invalid. Must be between 1 byte and 10 MB.",
                        max_size_mb=10,
                    )
                )
                continue

            validated_files.append((file_bytes, file.filename or "unknown", file.content_type or "application/octet-stream"))

        if errors:
            return errors, None

        return None, validated_files

    def upload_to_s3(
        self, user_id: str, validated_files: list[tuple[bytes, str, str]]
    ) -> tuple[str, list[IngestionFile]]:
        """Upload validated files to S3 and return job metadata.

        Generates a UUID4 job_id, uploads each file to S3, and returns
        the job_id along with IngestionFile metadata for each file.

        Args:
            user_id: The ID of the user uploading files.
            validated_files: List of (file_bytes, filename, content_type) tuples.

        Returns:
            A tuple of (job_id, list_of_IngestionFile_objects).

        Raises:
            S3UploadError: If any S3 put_object call fails.
        """
        job_id = str(uuid.uuid4())
        s3_client = get_s3_client()
        bucket = get_settings().S3_BUCKET
        ingestion_files: list[IngestionFile] = []

        try:
            for file_bytes, filename, content_type in validated_files:
                s3_key = construct_s3_key(user_id, job_id, filename)
                s3_client.put_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
                ingestion_files.append(
                    IngestionFile(
                        filename=filename,
                        mime_type=content_type,
                        size_bytes=len(file_bytes),
                        s3_key=s3_key,
                    )
                )
        except ClientError as e:
            raise S3UploadError(f"Failed to upload file to S3: {e}") from e

        return job_id, ingestion_files

    async def create_job_and_enqueue(
        self,
        job_id: str,
        user_id: str,
        ingestion_files: list[IngestionFile],
        background_tasks: BackgroundTasks,
    ) -> IngestionJobResponse:
        """Create a Job_Record in MongoDB and enqueue extraction as a background task.

        Args:
            job_id: The UUID job identifier.
            user_id: The ID of the user uploading files.
            ingestion_files: List of IngestionFile metadata for uploaded files.
            background_tasks: FastAPI BackgroundTasks for enqueuing extraction.

        Returns:
            An IngestionJobResponse with the job_id.
        """
        now = datetime.now(UTC)
        job_record = JobRecord(
            job_id=job_id,
            user_id=user_id,
            status=IngestionStatus.pending,
            files=ingestion_files,
            created_at=now,
            updated_at=now,
        )

        collection = get_ingestion_jobs_collection()
        await collection.insert_one(job_record.model_dump())

        background_tasks.add_task(self._run_extraction, job_id, user_id)

        return IngestionJobResponse(job_id=job_id)

    async def _run_extraction(self, job_id: str, user_id: str) -> None:
        """Run the full extraction pipeline for a job."""
        from app.services.extractor_service import ExtractorService
        from app.services.ingestion_router import IngestionRouter

        logger.info("Starting extraction for job %s", job_id)
        collection = get_ingestion_jobs_collection()
        job = await collection.find_one({"job_id": job_id})
        if not job:
            logger.error("Job %s not found — cannot extract", job_id)
            return

        # Mark job as 'processing' so the UI can show the correct status
        await collection.update_one(
            {"job_id": job_id},
            {"$set": {"status": "processing", "updated_at": datetime.now(UTC)}},
        )

        files = [IngestionFile(**f) for f in job["files"]]
        try:
            extraction_result = await ExtractorService().extract(job_id, files)
            await IngestionRouter().route(extraction_result, job_id=job_id, user_id=user_id)
        except Exception as exc:
            logger.error("Extraction pipeline failed for job %s: %s", job_id, exc)
            # Mark as failed if not already done by a downstream service
            refreshed = await collection.find_one({"job_id": job_id})
            if refreshed and refreshed.get("status") != "failed":
                await collection.update_one(
                    {"job_id": job_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error": str(exc),
                            "updated_at": datetime.now(UTC),
                        }
                    },
                )
