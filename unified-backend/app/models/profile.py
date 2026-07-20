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
    learning_context: LearningContext
    label: Optional[str] = Field(default=None, max_length=120)
    # e.g. "senior backend, Mumbai, 20 LPA" / "CBSE 9th standard, science stream"
    structured: dict[str, str] = {}
    # only populate keys the prompt actually branches on — validated against
    # ALLOWED_STRUCTURED_KEYS at write time by whichever service writes this
    # (not enforced by this model — see note below)


class GoalOrientation(str, Enum):
    MASTERY_APPROACH = "mastery_approach"           # wants to understand/improve, self-referenced
    MASTERY_AVOIDANCE = "mastery_avoidance"         # afraid of not meeting own standards
    PERFORMANCE_APPROACH = "performance_approach"   # wants to outperform others/benchmark
    PERFORMANCE_AVOIDANCE = "performance_avoidance" # afraid of looking incompetent
    OTHER = "other"


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
    may propose changes for. Deliberately narrow — proposals never touch
    onboarding-owned fields (learning_context, focus_areas, the three teaching
    preferences); those are direct user input, not inferred."""

    GOAL_ORIENTATION = "goal_orientation"
    STYLE_NOTE = "style_note"                          # one new note to add
    LEARNING_CONTEXT_STRUCTURED = "learning_context_structured"  # keys to merge in


class PendingProfileChange(BaseModel):
    """A proposed L1 change awaiting user accept/dismiss (never auto-applied).

    proposed_value's shape depends on `field`:
      - goal_orientation: {"value": "<GoalOrientation>"}
      - style_note: {"category": "<StyleNoteCategory>", "note": "<str>"}
      - learning_context_structured: {"<key>": "<value>", ...}
    """

    field: ProposableField
    proposed_value: dict
    reason: str = Field(max_length=200)  # short grounding text, shown to the user
    session_id: str
    created_at: datetime


# Write-time guard, meant to live in the profiling/session-reflection service that
# populates LearningContextDetail.structured — keeps it flexible while preventing
# silent key drift. Not enforced here; no writer for this field exists yet.
ALLOWED_STRUCTURED_KEYS: dict[LearningContext, set[str]] = {
    LearningContext.JOB_INTERVIEW: {"seniority_level", "target_comp", "location", "company_tier", "role_domain"},
    LearningContext.HIGH_STAKES_EXAM: {"board_or_syllabus", "grade_or_level"},
    LearningContext.COMPETITIVE_TEST: {"test_name", "target_score_or_rank"},
    LearningContext.SELF_DIRECTED: set(),  # label-only, no structured keys expected
    LearningContext.OTHER: set(),
}


class ProfileCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    learning_context: Optional[LearningContext] = None
    learning_context_detail: Optional[LearningContextDetail] = None

    goal_orientation: Optional[GoalOrientation] = None
    goal_orientation_custom: Optional[str] = Field(default=None, max_length=60)

    focus_areas: list[str] = []
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

    learning_context: Optional[LearningContext] = None
    learning_context_detail: Optional[LearningContextDetail] = None

    goal_orientation: Optional[GoalOrientation] = None
    goal_orientation_custom: Optional[str] = Field(default=None, max_length=60)

    focus_areas: Optional[list[str]] = None
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

    learning_context: Optional[LearningContext] = None
    learning_context_detail: Optional[LearningContextDetail] = None

    goal_orientation: Optional[GoalOrientation] = None
    goal_orientation_custom: Optional[str] = None

    focus_areas: list[str] = []
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
