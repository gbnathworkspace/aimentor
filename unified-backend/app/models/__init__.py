"""Pydantic data models for the unified backend."""

from app.models.profile import ProfileCreate, ProfileUpdate, ProfileResponse
from app.models.skill import SkillNode, SkillUpdate
from app.models.session import (
    Message,
    SessionCreate,
    SessionDoc,
    SessionDocument,
    SessionEndResult,
    SessionSkillUpdate,
    SessionStatus,
    SkillLevel,
)
from app.models.episodic import EpisodicEntry, SearchQuery
from app.models.ingestion import IngestionJobResponse
from app.models.chat import MentorRequest, MentorResponse, OnboardingRequest, OnboardingResponse
from app.models.document_upload import (
    DocumentUploadJob,
    L1SynthesisOutput,
    SynthesizedStyleNote,
    UploadFileRecord,
)

__all__ = [
    # Profile
    "ProfileCreate",
    "ProfileUpdate",
    "ProfileResponse",
    # Skill
    "SkillNode",
    "SkillUpdate",
    # Session
    "Message",
    "SessionCreate",
    "SessionDoc",
    "SessionDocument",
    "SessionEndResult",
    "SessionSkillUpdate",
    "SessionStatus",
    "SkillLevel",
    # Episodic
    "EpisodicEntry",
    "SearchQuery",
    # Ingestion
    "IngestionJobResponse",
    # Chat
    "MentorRequest",
    "MentorResponse",
    "OnboardingRequest",
    "OnboardingResponse",
    # Document Upload
    "DocumentUploadJob",
    "L1SynthesisOutput",
    "SynthesizedStyleNote",
    "UploadFileRecord",
]
