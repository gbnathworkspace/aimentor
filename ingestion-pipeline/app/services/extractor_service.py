"""Extractor service that routes files to the correct extractor based on MIME type."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config.database import get_ingestion_jobs_collection, get_s3_client
from app.config.settings import get_settings
from app.models.schemas import IngestionFile, LeetCodeTopicStats, ResumeSection
from app.services.extractors import CSVExtractionError, CSVExtractor, ExtractionError, PDFExtractor

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Combined extraction results from all files in a job."""

    resume_sections: list[ResumeSection] | None = None
    leetcode_stats: list[LeetCodeTopicStats] | None = None


class ExtractorService:
    """Routes files to the correct extractor based on MIME type.

    Downloads file bytes from S3 and dispatches to PDFExtractor or CSVExtractor
    based on the file's mime_type. On extraction failure, marks the job as 'failed'
    in MongoDB and re-raises the error.
    """

    def __init__(self) -> None:
        self._pdf_extractor = PDFExtractor()
        self._csv_extractor = CSVExtractor()

    async def extract(self, job_id: str, files: list[IngestionFile]) -> ExtractionResult:
        """Extract content from all files in a job.

        Args:
            job_id: The ingestion job identifier.
            files: List of IngestionFile objects with S3 keys and MIME types.

        Returns:
            ExtractionResult with resume_sections and/or leetcode_stats populated.

        Raises:
            ExtractionError: If PDF extraction fails.
            CSVExtractionError: If CSV extraction fails.
        """
        result = ExtractionResult()
        settings = get_settings()
        s3_client = get_s3_client()

        try:
            for file in files:
                file_bytes = self._download_from_s3(s3_client, settings.S3_BUCKET, file.s3_key)

                if file.mime_type == "application/pdf":
                    logger.info("Extracting PDF: %s", file.filename)
                    sections = self._pdf_extractor.extract(file_bytes)
                    result.resume_sections = sections

                elif file.mime_type == "text/csv":
                    logger.info("Extracting CSV: %s", file.filename)
                    stats = self._csv_extractor.extract(file_bytes)
                    result.leetcode_stats = stats

                else:
                    logger.warning(
                        "Unsupported MIME type '%s' for file '%s', skipping.",
                        file.mime_type,
                        file.filename,
                    )

        except (ExtractionError, CSVExtractionError) as exc:
            logger.error("Extraction failed for job %s: %s", job_id, exc)
            await self._mark_job_failed(job_id, str(exc))
            raise

        return result

    def _download_from_s3(self, s3_client, bucket: str, s3_key: str) -> bytes:
        """Download file bytes from S3.

        Args:
            s3_client: The boto3 S3 client.
            bucket: The S3 bucket name.
            s3_key: The object key in S3.

        Returns:
            Raw file bytes.
        """
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        return response["Body"].read()

    async def _mark_job_failed(self, job_id: str, error_message: str) -> None:
        """Mark the job as 'failed' in MongoDB with the error message.

        Args:
            job_id: The ingestion job identifier.
            error_message: User-facing error description.
        """
        collection = get_ingestion_jobs_collection()
        await collection.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": error_message,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        logger.info("Marked job %s as failed: %s", job_id, error_message)
