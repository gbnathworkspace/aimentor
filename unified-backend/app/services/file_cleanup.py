"""File cleanup service for expired document uploads.

Provides functions to:
- Delete upload files for a specific job
- Periodically scan and remove orphaned upload directories whose
  MongoDB Upload_Job records have expired (TTL-deleted)

The MongoDB TTL index on `expires_at` handles document record cleanup.
This module handles the corresponding file system cleanup.
"""

import asyncio
import logging
import shutil
from pathlib import Path

from app.config.database import document_upload_jobs_col

logger = logging.getLogger(__name__)

# Base directory matching the documents router
UPLOADS_BASE_DIR = Path("uploads")


def delete_upload_files(user_id: str, job_id: str) -> bool:
    """Delete the upload directory for a specific job.

    Args:
        user_id: The user who owns the upload.
        job_id: The job ID whose files should be deleted.

    Returns:
        True if the directory was deleted, False if it didn't exist.
    """
    job_dir = UPLOADS_BASE_DIR / user_id / job_id
    if job_dir.is_dir():
        shutil.rmtree(job_dir)
        logger.info("Deleted upload directory: %s", job_dir)
        return True
    return False


async def cleanup_expired_uploads() -> int:
    """Scan the uploads/ directory and remove orphaned job directories.

    A job directory is considered orphaned when its corresponding
    Upload_Job record no longer exists in MongoDB (removed by TTL index).

    Also removes empty user directories after cleaning up job directories.

    Returns:
        The number of orphaned directories removed.
    """
    removed_count = 0

    if not UPLOADS_BASE_DIR.is_dir():
        return removed_count

    col = document_upload_jobs_col()

    # Iterate over user directories
    for user_dir in UPLOADS_BASE_DIR.iterdir():
        if not user_dir.is_dir():
            continue

        user_id = user_dir.name

        # Iterate over job directories within each user directory
        for job_dir in user_dir.iterdir():
            if not job_dir.is_dir():
                continue

            job_id = job_dir.name

            # Check if the Upload_Job record still exists in MongoDB
            job_record = await col.find_one(
                {"job_id": job_id, "user_id": user_id},
                {"_id": 1},
            )

            if job_record is None:
                # Record has been TTL-deleted — remove files
                try:
                    shutil.rmtree(job_dir)
                    removed_count += 1
                    logger.info(
                        "Cleaned up orphaned upload directory: %s/%s",
                        user_id,
                        job_id,
                    )
                except OSError as exc:
                    logger.warning(
                        "Failed to remove orphaned directory %s: %s",
                        job_dir,
                        exc,
                    )

        # Remove empty user directory after cleanup
        try:
            if user_dir.is_dir() and not any(user_dir.iterdir()):
                user_dir.rmdir()
                logger.debug("Removed empty user directory: %s", user_dir)
        except OSError:
            pass  # Race condition or permissions — not critical

    return removed_count


async def file_cleanup_loop(interval_seconds: int = 3600) -> None:
    """Background loop that runs cleanup_expired_uploads periodically.

    Args:
        interval_seconds: Time between cleanup runs (default: 1 hour).
    """
    while True:
        try:
            removed = await cleanup_expired_uploads()
            if removed:
                logger.info(
                    "File cleanup sweep: removed %d orphaned directories",
                    removed,
                )
        except Exception:
            logger.exception("Error during file cleanup sweep")
        await asyncio.sleep(interval_seconds)
