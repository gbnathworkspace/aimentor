"""PDF/CSV extraction, text chunking, and embedding storage.

Provides functions to extract text from PDF and CSV files,
split text into overlapping chunks, and process ingestion jobs
as background tasks (embedding each chunk via Voyage AI and
storing results in MongoDB).
"""

import csv
import io
import logging
import os
from datetime import datetime, timezone

from pypdf import PdfReader

from app.config.database import ingestion_jobs_col
from app.services.vector_search import embed_and_upsert

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pypdf.

    Args:
        file_path: Path to the PDF file on disk (or S3 key for local storage).

    Returns:
        Concatenated text from all pages of the PDF.

    Raises:
        Exception: If the PDF cannot be read or parsed.
    """
    reader = PdfReader(file_path)
    pages_text: list[str] = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)

    return "\n".join(pages_text)


def extract_text_from_csv(file_path: str) -> str:
    """Parse CSV and convert to text format (headers + rows).

    Each row is formatted as a line with "header: value" pairs,
    making the content suitable for embedding and semantic search.

    Args:
        file_path: Path to the CSV file.

    Returns:
        Text representation of the CSV data.

    Raises:
        Exception: If the CSV cannot be read or parsed.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        rows_text: list[str] = []

        for row in reader:
            row_parts = [f"{key}: {value}" for key, value in row.items() if value]
            if row_parts:
                rows_text.append(" | ".join(row_parts))

    return "\n".join(rows_text)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks.

    Creates chunks of approximately `chunk_size` characters with
    `overlap` characters of overlap between consecutive chunks.
    This ensures context continuity across chunk boundaries.

    Args:
        text: The input text to split.
        chunk_size: Target size of each chunk in characters.
        overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        A list of text chunks.
    """
    if not text or not text.strip():
        return []

    # Ensure overlap is less than chunk_size to avoid infinite loops
    if overlap >= chunk_size:
        overlap = chunk_size // 2

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # If this isn't the last chunk, try to break at a whitespace boundary
        if end < text_len:
            # Look for the last whitespace within the chunk
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move forward by chunk_size - overlap
        start = start + chunk_size - overlap

        # Avoid infinite loop if overlap >= chunk_size
        if start <= (end - chunk_size + overlap) and chunks:
            start = end

    return chunks


async def process_extraction(
    job_id: str, user_id: str, file_paths: list[str]
) -> None:
    """Main extraction function — runs as a FastAPI background task.

    For each file path:
    1. Detect file type (PDF or CSV) based on extension
    2. Extract text content
    3. Chunk the text into overlapping segments
    4. Embed each chunk via Voyage AI
    5. Store chunks with embeddings in the embeddings collection

    Updates the ingestion job status to "completed" on success
    or "failed" with error message on failure.

    Args:
        job_id: The ingestion job ID.
        user_id: The authenticated user's ID.
        file_paths: List of file paths to process.
    """
    try:
        for file_path in file_paths:
            # Detect file type from extension
            ext = os.path.splitext(file_path)[1].lower()
            filename = os.path.basename(file_path)

            if ext == ".pdf":
                text = extract_text_from_pdf(file_path)
            elif ext == ".csv":
                text = extract_text_from_csv(file_path)
            else:
                raise ValueError(f"Unsupported file type: {ext}")

            if not text or not text.strip():
                logger.warning(
                    "No text extracted from file %s (job %s)", filename, job_id
                )
                continue

            # Chunk the extracted text
            chunks = chunk_text(text)

            if not chunks:
                logger.warning(
                    "No chunks produced from file %s (job %s)", filename, job_id
                )
                continue

            # Embed and store each chunk
            for chunk_index, chunk in enumerate(chunks):
                await embed_and_upsert(
                    vector_id=f"{job_id}:{chunk_index}",
                    text=chunk,
                    user_id=user_id,
                    source="ingestion",
                    metadata={"filename": filename, "chunk_index": chunk_index, "job_id": job_id},
                )

        # Mark job as completed
        await ingestion_jobs_col().update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        logger.info("Ingestion job %s completed successfully", job_id)

    except Exception as e:
        logger.error("Ingestion job %s failed: %s", job_id, str(e))
        # Mark job as failed with error message
        await ingestion_jobs_col().update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(e),
                }
            },
        )


async def process_topic_document(
    topic_id: str, user_id: str, file_paths: list[tuple[str, str]]
) -> None:
    """Extract, chunk, and embed a document as context scoped to one topic.

    Unlike process_extraction (onboarding, source="ingestion", user-wide),
    these chunks carry metadata.topic_id and source="topic_document" — picked
    up by context_assembler._fetch_documents for that topic only. No job
    tracking: topic documents are small notes/syllabi, processed inline by
    a background task, not worth a status-polling endpoint.

    Args:
        topic_id: The topic this document is scoped to.
        user_id: The authenticated user's ID.
        file_paths: List of (file_path, filename) tuples to process.
    """
    uploaded_at = datetime.now(timezone.utc).isoformat()
    for file_path, filename in file_paths:
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".pdf":
                text = extract_text_from_pdf(file_path)
            elif ext == ".csv":
                text = extract_text_from_csv(file_path)
            else:
                logger.warning("Unsupported file type %s for topic=%s", ext, topic_id)
                continue

            if not text or not text.strip():
                logger.warning("No text extracted from %s for topic=%s", filename, topic_id)
                continue

            chunks = chunk_text(text)
            for chunk_index, chunk in enumerate(chunks):
                await embed_and_upsert(
                    vector_id=f"topic:{topic_id}:{filename}:{chunk_index}",
                    text=chunk,
                    user_id=user_id,
                    source="topic_document",
                    metadata={
                        "filename": filename, "chunk_index": chunk_index,
                        "topic_id": topic_id, "uploaded_at": uploaded_at,
                    },
                )
        except Exception:
            logger.exception("Topic document processing failed for %s (topic=%s)", filename, topic_id)
