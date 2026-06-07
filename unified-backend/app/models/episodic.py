"""L3 Episodic Memory Pydantic models."""

from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class EpisodicEntry(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    topic: str
    topic_category: Optional[str] = None
    type: str = "session"
    date: str
    title: str
    summary: str
    skill_update: Optional[dict] = None


class SearchQuery(BaseModel):
    query: str
    limit: int = 3
    topic: Optional[str] = None
