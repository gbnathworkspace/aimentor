"""Chat request/response Pydantic models."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.session import Message

# The four supported mentor session modes. Constraining the API boundary to this
# set turns an unknown/corrupted mode into a 422 at request-validation time,
# instead of an uncaught ValueError → 500 inside get_system_prompt (issue #6).
MentorMode = Literal["planning", "topic", "doubt", "evaluation"]

# Mentor voice. Same boundary contract as MentorMode: an unknown tone is a 422,
# never a silently-dropped field. Behavioral text for each tone lives in
# prompt_store._TONE_INSTRUCTIONS — this is just the id contract + default.
ToneId = Literal["tough", "balanced", "encouraging"]
DEFAULT_TONE: ToneId = "balanced"


class MentorRequest(BaseModel):
    """Request body for POST /api/mentor."""

    model_config = ConfigDict(populate_by_name=True)

    topic: str
    mode: MentorMode = "topic"
    tone: ToneId = DEFAULT_TONE
    messages: list[Message]
    session_id: Optional[str] = Field(None, alias="sessionId")


class MentorResponse(BaseModel):
    """Response body for POST /api/mentor."""

    text: str


class OnboardingRequest(BaseModel):
    """Request body for POST /api/onboarding/chat."""

    messages: list[Message]


class OnboardingSuggestion(BaseModel):
    """A single tappable reply option offered during onboarding."""

    title: str
    description: str


class OnboardingResponse(BaseModel):
    """Response body for POST /api/onboarding/chat."""

    model_config = ConfigDict(populate_by_name=True)

    text: str
    suggestions: list[OnboardingSuggestion] = []
    complete: bool = False
    # Key is `profile` to match the frontend/Next contract (read as `profile`).
    profile: Optional[dict] = None


class OnboardingCompleteRequest(BaseModel):
    """Request body for POST /api/onboarding/complete."""

    model_config = ConfigDict(populate_by_name=True)

    goal: str
    deadline: str
    overall_level: str = Field("beginner", alias="overallLevel")
    daily_availability: str = Field("2 hrs/day", alias="dailyAvailability")


class OnboardingCompleteResponse(BaseModel):
    """Response body for POST /api/onboarding/complete."""

    model_config = ConfigDict(populate_by_name=True)

    skills: list[dict]


class OnboardingSkipRequest(BaseModel):
    """Request body for POST /api/onboarding/skip."""

    partial_profile: Optional[dict] = Field(None, alias="partialProfile")

    model_config = ConfigDict(populate_by_name=True)


class OnboardingSkipResponse(BaseModel):
    """Response body for POST /api/onboarding/skip."""

    ok: bool
    session_id: str = Field("", alias="sessionId")

    model_config = ConfigDict(populate_by_name=True)


class OnboardingCompleteDeferredRequest(BaseModel):
    """Request body for POST /api/onboarding/complete-deferred."""

    goal: Optional[str] = None
    deadline: Optional[str] = None
    overall_level: Optional[str] = Field(None, alias="overallLevel")
    daily_availability: Optional[str] = Field(None, alias="dailyAvailability")

    model_config = ConfigDict(populate_by_name=True)


class OnboardingCompleteDeferredResponse(BaseModel):
    """Response body for POST /api/onboarding/complete-deferred."""

    ok: bool
