"""L1 Profile Pydantic models."""

from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ProfileCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    goal: str
    deadline: str
    overall_level: str = "beginner"
    daily_availability: str = "2 hrs/day"
    email: Optional[str] = None


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    goal: Optional[str] = None
    deadline: Optional[str] = None
    overall_level: Optional[str] = None
    daily_availability: Optional[str] = None
    email: Optional[str] = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    user_id: str
    goal: str
    deadline: str
    overall_level: str
    daily_availability: str
    email: Optional[str] = None
