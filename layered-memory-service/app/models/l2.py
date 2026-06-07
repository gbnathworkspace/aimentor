from pydantic import BaseModel
from typing import Any, Optional


class SkillNode(BaseModel):
    topic: str
    required_level: str
    current_level: str
    gap: str
    signals: dict[str, Any] = {}


class SkillUpdate(BaseModel):
    required_level: Optional[str] = None
    current_level: Optional[str] = None
    gap: Optional[str] = None
    signals: Optional[dict[str, Any]] = None
