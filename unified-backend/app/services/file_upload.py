"""Upload validation, S3/local storage."""

import os
from pathlib import Path

import boto3
from fastapi import UploadFile

from app.config.settings import get_settings

# Allowed MIME types for ingestion
ALLOWED_MIME_TYPES = {"application/pdf", "text/csv"}

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024


async def validate_files(
    files: list[UploadFile],
) -> tuple[list[UploadFile], list[dict]]:
    """Validate uploaded files for allowed MIME type and size.

    Returns a tuple of (valid_files, errors) where errors is a list of
    dicts with 'filename' and 'error' keys describing each rejection reason.
    """
    valid_files: list[UploadFile] = []
    errors: list[dict] = []

    for file in files:
        filename = file.filename or "unknown"

        # Check MIME type
        if file.content_type not in ALLOWED_MIME_TYPES:
            errors.append(
                {
                    "filename": filename,
                    "error": (
                        f"Unsupported file type '{file.content_type}'. "
                        f"Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
                    ),
                }
            )
            continue

        # Check file size by reading content
        content = await file.read()
        await file.seek(0)  # Reset for later consumption

        if len(content) > MAX_FILE_SIZE:
            errors.append(
                {
                    "filename": filename,
                    "error": (
                        f"File size ({len(content)} bytes) exceeds maximum "
                        f"allowed size ({MAX_FILE_SIZE} bytes / 50MB)"
                    ),
                }
            )
            continue

        valid_files.append(file)

    return valid_files, errors


async def store_file(file: UploadFile, user_id: str, job_id: str) -> str:
    """Store an uploaded file using the configured storage backend.

    Args:
        file: The validated UploadFile to store.
        user_id: The authenticated user's ID.
        job_id: The ingestion job ID for organizing uploads.

    Returns:
        The file path (local) or S3 key where the file was stored.
    """
    settings = get_settings()
    filename = file.filename or "unknown"

    if settings.STORAGE_BACKEND == "s3":
        return await _store_s3(file, user_id, job_id, filename, settings)
    else:
        return await _store_local(file, user_id, job_id, filename)


async def _store_local(
    file: UploadFile, user_id: str, job_id: str, filename: str
) -> str:
    """Store file on local disk under uploads/{user_id}/{job_id}/{filename}."""
    upload_dir = Path("uploads") / user_id / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / filename
    content = await file.read()

    with open(file_path, "wb") as f:
        f.write(content)

    return str(file_path)


async def _store_s3(
    file: UploadFile,
    user_id: str,
    job_id: str,
    filename: str,
    settings,
) -> str:
    """Upload file to S3 at key {user_id}/{job_id}/{filename}."""
    s3_client = boto3.client(
        "s3",
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    key = f"{user_id}/{job_id}/{filename}"
    content = await file.read()

    s3_client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )

    return key
