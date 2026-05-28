from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


# ── Layer 1: Core Profile ────────────────────────────────────────────

class CoreProfile(BaseModel):
    user_id: str
    goal: str
    deadline: str
    overall_level: str
    daily_availability: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Layer 2: Skill Graph ─────────────────────────────────────────────

class SkillSignals(BaseModel):
    leetcode_solved: dict = Field(default_factory=dict)
    mentor_eval_score: Optional[str] = None
    weak_areas: list[str] = Field(default_factory=list)
    strong_areas: list[str] = Field(default_factory=list)


class SkillNode(BaseModel):
    user_id: str
    topic: str
    current_level: Literal["easy", "medium", "hard", "unknown"] = "unknown"
    required_level: Literal["easy", "medium", "hard", "basic"] = "medium"
    gap: str = "unknown"
    last_studied: Optional[str] = None
    signals: SkillSignals = Field(default_factory=SkillSignals)


# ── Layer 3: Session / Episodic ──────────────────────────────────────

class SessionMode(str):
    PLANNING = "planning"
    TOPIC = "topic_session"
    DOUBT = "doubt_resolution"
    EVALUATION = "evaluation"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    mode: str = "topic_session"
    topic: Optional[str] = None
    topic_category: Optional[str] = None
    title: Optional[str] = None
    transcript: list[ChatMessage] = Field(default_factory=list)
    summary: Optional[str] = None
    skill_update: Optional[dict] = None


# ── Session End Output ───────────────────────────────────────────────

class SkillUpdate(BaseModel):
    topic: str
    current_level: Literal["easy", "medium", "hard"]
    weak_areas: list[str] = Field(default_factory=list)
    strong_areas: list[str] = Field(default_factory=list)
    mock_score: Optional[str] = None
    last_studied: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))


class SessionEndOutput(BaseModel):
    narrative_summary: str
    skill_update: SkillUpdate


# ── API Request/Response ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    topic: Optional[str] = None
    topic_category: Optional[str] = None


class SessionStartRequest(BaseModel):
    user_id: str
    mode: str = "topic_session"
    topic: Optional[str] = None
    topic_category: Optional[str] = None


class SessionEndRequest(BaseModel):
    session_id: str
    user_id: str
