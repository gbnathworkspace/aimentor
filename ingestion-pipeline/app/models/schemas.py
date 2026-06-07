"""Pydantic data models and enums for the ingestion pipeline."""

from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IngestionStatus(str, Enum):
    """Status of an ingestion job throughout its lifecycle."""

    pending = "pending"
    processing = "processing"
    done = "done"
    partial = "partial"
    failed = "failed"


class IngestionFile(BaseModel):
    """Metadata for an uploaded file within an ingestion job."""

    filename: str
    mime_type: str
    size_bytes: int
    s3_key: str


class JobRecord(BaseModel):
    """Ingestion job record stored in the ingestion_jobs MongoDB collection."""

    job_id: str
    user_id: str
    status: IngestionStatus
    files: list[IngestionFile]
    error: Optional[str] = None
    structured_done: bool = False
    embedding_done: bool = False
    source_category: Optional[str] = None
    last_reingested_at: Optional[str] = None
    session_id: Optional[str] = None
    upload_context: Optional[str] = None
    accompanying_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class IngestionJobResponse(BaseModel):
    """Response returned immediately after a successful upload."""

    job_id: str


class FileValidationError(BaseModel):
    """Error details when file validation fails."""

    field: str
    message: str
    supported_types: Optional[list[str]] = None
    max_size_mb: Optional[int] = None


class ResumeSection(BaseModel):
    """A detected section from a parsed resume PDF."""

    section: str
    text: str
    order: int
    sub_entries: list[str] = Field(default_factory=list)


class LeetCodeTopicStats(BaseModel):
    """Aggregated LeetCode problem counts per topic and difficulty."""

    topic: str
    easy: int
    medium: int
    hard: int


class ChunkMetadata(BaseModel):
    """Metadata attached to each text chunk for retrieval and filtering."""

    user_id: str
    source: str
    section: Optional[str] = None
    chunk_index: int
    topic: Optional[str] = None
    job_id: Optional[str] = None
    topic_category: Optional[str] = None
    session_id: Optional[str] = None
    upload_context: Optional[str] = None
    date: Optional[str] = None
    type: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chunk(BaseModel):
    """A text chunk ready for embedding, with associated metadata."""

    text: str
    metadata: ChunkMetadata


class CoreProfileIngestion(BaseModel):
    """Structured profile fields extracted from resume during ingestion."""

    current_role: Optional[str] = None
    years_of_experience: Optional[int] = None
    education: Optional[str] = None
    skills: list[str] = Field(default_factory=list)


class LeetCodeCounts(BaseModel):
    """Per-difficulty solve counts for a skill graph node."""

    easy: int = 0
    medium: int = 0
    hard: int = 0


class SkillGraphSignals(BaseModel):
    """Signal data stored in the skill_graph collection per topic."""

    leetcode_solved: Optional[LeetCodeCounts] = None
    mentor_eval_score: Optional[str] = None
    mentor_eval_count: int = 0


class VectorChunk(BaseModel):
    """A chunk stored in Atlas Vector Search with its embedding vector."""

    vector: list[float]
    text: str
    metadata: ChunkMetadata


class SessionCheckpoint(BaseModel):
    """Checkpoint fields for session data preservation."""

    transcript: list[dict]
    last_checkpoint_turn: int
    orphaned: bool = False
    recovered: bool = False
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None


class SessionEndOutput(BaseModel):
    """Output from the LLM session summarization step."""

    narrative_summary: str
    skill_update: dict
