"""Session Pydantic models."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    title: str = "Untitled session"
    mode: str = "topic"
    topic: Optional[str] = None
    topic_category: Optional[str] = None


class SessionDoc(BaseModel):
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
