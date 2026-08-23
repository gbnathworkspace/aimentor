"""L1 Profile Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class LearningContext(str, Enum):
    HIGH_STAKES_EXAM = "high_stakes_exam"      # school/board exams, externally mandated
    COMPETITIVE_TEST = "competitive_test"       # entrance/standardized tests, ranked outcome
    JOB_INTERVIEW = "job_interview"
    SELF_DIRECTED = "self_directed"             # casual study, no external deadline
    OTHER = "other"


class LearningContextDetail(BaseModel):
    # Free text like `situations` below — LearningContext's members remain as
    # well-known defaults, but the field itself no longer restricts users to
    # those 5 values.
    learning_context: str = Field(max_length=60)
    label: Optional[str] = Field(default=None, max_length=120)
    # e.g. "senior backend, Mumbai, 20 LPA" / "CBSE 9th standard, science stream"
    # Free-text facts about the user (e.g. "leading the backend rewrite",
    # "interviewing for senior roles"). All are injected — none is "active".
    # FIFO-capped, newest first; `label` mirrors the first entry for readers
    # that predate this list. There is no separate `contexts` field any
    # more — it duplicated this same list with no UI of its own (see
    # l1_scope.extract_situations, which folds `learning_context` in here
    # too instead of keeping a second parallel list).
    situations: list[str] = Field(default_factory=list, max_length=20)


class StyleNoteCategory(str, Enum):
    PACING = "pacing"                # rushes, skips edge cases, wants to move fast/slow
    COMMUNICATION = "communication"  # prefers examples over theory, terse vs verbose
    MOTIVATION = "motivation"        # what keeps them engaged / what disengages them
    MISCONCEPTION = "misconception"  # recurring wrong mental model, not skill-specific
    CONTEXT = "context"              # life/schedule constraints affecting learning


class StyleNote(BaseModel):
    category: StyleNoteCategory
    note: str = Field(max_length=140)     # the extracted claim, kept short
    source_quote: str                     # verbatim snippet it was grounded in — required
    session_id: str                       # traceability back to when this was observed
    added_at: datetime


class ProposableField(str, Enum):
    """Fields the post-session profiling agent (app/services/profiling_agent.py)
    or the document upload pipeline may propose changes for.

    Session-derived proposals cover style_note. Document-upload proposals
    additionally cover situation (appended to learning_context_detail.situations,
    i.e. "Facts About You")."""

    STYLE_NOTE = "style_note"                          # one new note to add
    SITUATION = "situation"                            # one new fact to append


class PendingProfileChange(BaseModel):
    """A proposed L1 change awaiting user accept/dismiss (never auto-applied).

    proposed_value's shape depends on `field`:
      - style_note: {"category": "<StyleNoteCategory>", "note": "<str>"}
      - situation: {"value": "<str>"}
    """

    field: ProposableField
    proposed_value: dict
    reason: str = Field(max_length=200)  # short grounding text, shown to the user
    session_id: str  # For document uploads, stores the job_id for traceability
    created_at: datetime
    # Distinguishes source of the proposal. None or "session" for profiling-agent
    # proposals; "document_upload" for proposals from the document upload pipeline.
    source_type: Optional[str] = None


class ProfileCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    learning_context: Optional[str] = Field(default=None, max_length=60)
    learning_context_detail: Optional[LearningContextDetail] = None

    explanation_style: Literal["hint-first", "answer-first"] = "hint-first"
    challenge_tolerance: Literal["low", "medium", "high"] = "medium"
    feedback_tone: Literal["direct", "encouraging"] = "encouraging"
    style_notes: list[StyleNote] = Field(default_factory=list, max_length=5)

    email: Optional[str] = None
    profile_status: Literal["complete", "skipped"] = "complete"
    name: Optional[str] = None
    # Profile picture as a data URI (data:image/...;base64,...); see MAX_AVATAR_BYTES.
    avatar: Optional[str] = None


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    learning_context: Optional[str] = Field(default=None, max_length=60)
    learning_context_detail: Optional[LearningContextDetail] = None

    explanation_style: Optional[Literal["hint-first", "answer-first"]] = None
    challenge_tolerance: Optional[Literal["low", "medium", "high"]] = None
    feedback_tone: Optional[Literal["direct", "encouraging"]] = None
    style_notes: Optional[list[StyleNote]] = Field(default=None, max_length=5)

    email: Optional[str] = None
    profile_status: Optional[Literal["complete", "skipped"]] = None
    name: Optional[str] = None
    avatar: Optional[str] = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    user_id: str

    learning_context: Optional[str] = Field(default=None, max_length=60)
    learning_context_detail: Optional[LearningContextDetail] = None

    explanation_style: Literal["hint-first", "answer-first"] = "hint-first"
    challenge_tolerance: Literal["low", "medium", "high"] = "medium"
    feedback_tone: Literal["direct", "encouraging"] = "encouraging"
    style_notes: list[StyleNote] = []
    # Proposed by the post-session profiling agent, awaiting accept/dismiss via
    # POST /api/profile/pending-changes/{field}/(accept|dismiss). Never written
    # by ProfileCreate/ProfileUpdate — system-managed only.
    pending_changes: list[PendingProfileChange] = []

    email: Optional[str] = None
    profile_status: Literal["complete", "skipped"] = "complete"
    name: Optional[str] = None
    avatar: Optional[str] = None
