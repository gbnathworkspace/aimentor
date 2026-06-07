"""Chat request/response Pydantic models."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.session import Message


class MentorRequest(BaseModel):
    """Request body for POST /api/mentor."""

    model_config = ConfigDict(populate_by_name=True)

    topic: str
    mode: str = "topic"
    messages: list[Message]
    session_id: Optional[str] = Field(None, alias="sessionId")


class MentorResponse(BaseModel):
    """Response body for POST /api/mentor."""

    text: str


class OnboardingRequest(BaseModel):
    """Request body for POST /api/onboarding/chat."""

    messages: list[Message]


class OnboardingResponse(BaseModel):
    """Response body for POST /api/onboarding/chat."""

    model_config = ConfigDict(populate_by_name=True)

    text: str
    suggestions: list[str] = []
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
