from pydantic import BaseModel
from typing import Optional


class SkillUpdateSnapshot(BaseModel):
    current_level: Optional[str] = None
    weak_areas: list[str] = []
    strong_areas: list[str] = []


class EpisodicEntry(BaseModel):
    topic: str
    topic_category: str
    type: str
    date: str
    title: str
    summary: str
    skill_update: Optional[SkillUpdateSnapshot] = None


class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    topic: Optional[str] = None
