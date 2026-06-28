"""Session Pydantic models for session persistence pipeline."""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class SessionStatus(str, Enum):
    """Lifecycle status of a session: active → ending → ended."""

    active = "active"
    ending = "ending"
    ended = "ended"


class SkillLevel(str, Enum):
    """Valid skill levels for LLM-extracted skill updates.

    Canonical vocabulary shared with the skill graph (onboarding_bootstrap.
    LEVEL_ORDER) so session output feeds compute_gap/planning without translation.
    """

    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


class Message(BaseModel):
    """A single chat message within a session.

    Accepts both 'assistant' (legacy) and 'mentor' (new spec) roles for
    backward compatibility with existing code.
    """

    role: Literal["user", "assistant", "mentor"]
    content: str = Field(..., max_length=50_000)
    timestamp: Optional[str] = None


class SessionSkillUpdate(BaseModel):
    """Structured skill update extracted from session by the LLM.

    Matches the SkillUpdateToolSchema Zod schema used in the frontend.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    topic: str
    new_level: SkillLevel = Field(..., alias="new_level")
    gap: int = Field(..., ge=0, le=100)
    weak_areas: list[str] = Field(default_factory=list, max_length=10)
    strong_areas: list[str] = Field(default_factory=list, max_length=10)
    eval_score: Optional[str] = None

    @field_validator("weak_areas", "strong_areas", mode="before")
    @classmethod
    def truncate_areas(cls, v: list[str]) -> list[str]:
        """Ensure at most 10 items in area lists."""
        if isinstance(v, list) and len(v) > 10:
            return v[:10]
        return v


class SessionCreate(BaseModel):
    """Request body for creating a new session."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    title: str = "Untitled session"
    mode: str = "topic"
    topic: Optional[str] = None
    topic_category: Optional[str] = None


class SessionDoc(BaseModel):
    """Minimal session document model (legacy, used by existing endpoints)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    session_id: str
    user_id: str
    title: str
    mode: str
    topic: Optional[str] = None
    status: str = "active"
    messages: list[Message] = []
    tags: list[str] = []
    summary: Optional[str] = None
    created_at: str
    updated_at: str


class SessionDocument(BaseModel):
    """Full session document stored in MongoDB sessions collection.

    Extends the legacy SessionDoc with all fields required by the
    session persistence pipeline.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    session_id: str = Field(..., description="UUID v4 session identifier")
    user_id: str = Field(..., description="Clerk user ID")
    title: str = Field(default="Untitled session")
    mode: str = Field(..., description="Session mode: topic | planning | doubt | evaluation")
    topic: Optional[str] = None
    topic_category: Optional[str] = None
    status: SessionStatus = SessionStatus.active
    messages: list[Message] = Field(default_factory=list)
    summary: Optional[str] = Field(None, description="Narrative summary (3-5 sentences)")
    skill_update: Optional[SessionSkillUpdate] = None
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(..., description="ISO-8601 UTC timestamp")
    updated_at: str = Field(..., description="ISO-8601 UTC timestamp")
    ended_at: Optional[str] = Field(None, description="ISO-8601 UTC, set on transition to ended")
    failure_reason: Optional[str] = Field(
        None, description="Set if end-processing failed or timed out"
    )


class SessionEndResult(BaseModel):
    """Response model returned after session-end processing completes."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    session_id: str
    title: str
    summary: str
    skill_update: Optional[SessionSkillUpdate] = None
    # Level change for this session's topic, for a "you leveled up" tag (issue #16).
    # Both None when the session didn't produce a skill update.
    level_from: Optional[str] = None
    level_to: Optional[str] = None
    status: Literal["ended"] = "ended"
