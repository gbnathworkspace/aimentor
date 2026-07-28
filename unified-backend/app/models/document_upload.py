"""Data models for the chat document upload pipeline.

Defines the Upload_Job record (DocumentUploadJob), per-file tracking
(UploadFileRecord), and LLM synthesis output schemas (L1SynthesisOutput,
SynthesizedStyleNote).

These models support the Document Ingestion Pipeline which is fully
independent from the existing IngestionService.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.profile import StyleNoteCategory


class UploadFileRecord(BaseModel):
    """Tracks the status of a single uploaded file within an Upload_Job.

    Attributes:
        filename: Original filename of the uploaded document.
        mime_type: MIME type of the file (e.g. 'application/pdf').
        file_path: Local storage path where the file is saved.
        size_bytes: File size in bytes.
        status: Current extraction status for this file.
        error: Error message if extraction failed, None otherwise.
    """

    filename: str
    mime_type: str
    file_path: str
    size_bytes: int
    status: Literal["pending", "extracted", "failed"] = "pending"
    error: Optional[str] = None


class DocumentUploadJob(BaseModel):
    """Represents a tracked unit of work for a batch of uploaded documents.

    Stored in the `document_upload_jobs` MongoDB collection with a TTL
    index on `expires_at` for automatic cleanup after 24 hours.

    Attributes:
        job_id: Unique identifier (UUID) for this upload job.
        user_id: ID of the authenticated user who initiated the upload.
        status: Current pipeline stage for the job.
        files: List of per-file tracking records.
        skip_review: Whether to bypass user confirmation and write directly.
        message: Optional accompanying chat message from the user.
        extracted_text: Combined text from all files (preserved for retry).
        proposals: List of validated L1 field proposal dicts when synthesis completes.
        proposal_count: Number of proposals generated (0 if none).
        created_at: Timestamp when the job was created.
        updated_at: Timestamp of the last status update.
        expires_at: TTL expiration timestamp (created_at + 24 hours).
    """

    job_id: str
    user_id: str
    status: Literal["pending", "extracting", "synthesizing", "done", "failed"] = "pending"
    files: list[UploadFileRecord] = Field(default_factory=list)
    skip_review: bool = False
    message: Optional[str] = None
    extracted_text: Optional[str] = None
    proposals: Optional[list[dict]] = None
    proposal_count: int = 0
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class SynthesizedStyleNote(BaseModel):
    """A style note proposal produced by LLM synthesis.

    Attributes:
        category: The style note category (from StyleNoteCategory enum).
        note: The extracted claim, kept short (max 140 chars).
        source_quote: Verbatim span from extracted text (max 200 chars).
    """

    category: StyleNoteCategory
    note: str = Field(max_length=140)
    source_quote: str = Field(max_length=200)


class L1SynthesisOutput(BaseModel):
    """Expected structured output from the LLM synthesis call.

    Represents the parsed LLM response containing proposed L1 field
    updates extracted from uploaded documents.

    Attributes:
        style_notes: Proposed style note entries with source quotes.
        focus_areas: Proposed focus area strings (max 60 chars each).
    """

    style_notes: Optional[list[SynthesizedStyleNote]] = None
    focus_areas: Optional[list[str]] = None
