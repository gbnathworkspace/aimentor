"""L2 Skill Graph Pydantic models."""

from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SkillNode(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    topic: str
    required_level: str = "intermediate"
    current_level: str = "beginner"
    previous_level: Optional[str] = None  # level before the last session (issue #16)
    gap: str = "medium"
    signals: Optional[dict] = None
    prerequisites: list[str] = []  # topics to master first, for planning sequencing (issue #10)


class SkillUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    required_level: Optional[str] = None
    current_level: Optional[str] = None
    gap: Optional[str] = None
    signals: Optional[dict] = None
