import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import verify_api_key
from app.memory.l2.crud import upsert_skill
from app.memory.l3.crud import save_session
from app.models.l2 import SkillUpdate
from app.models.l3 import EpisodicEntry
from app.services import claude

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Session"], dependencies=[Depends(verify_api_key)])

_SUMMARISE_TOOL = {
    "name": "save_session_summary",
    "description": "Produce a structured summary of the learning session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title for the session (≤8 words)"},
            "narrative_summary": {"type": "string", "description": "2-4 sentence narrative of what was covered and how the learner did"},
            "skill_update": {
                "type": "object",
                "properties": {
                    "current_level": {"type": "string", "enum": ["beginner", "intermediate", "advanced", "expert"]},
                    "weak_areas": {"type": "array", "items": {"type": "string"}},
                    "strong_areas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["current_level"],
            },
        },
        "required": ["title", "narrative_summary"],
    },
}


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionEndRequest(BaseModel):
    user_id: str
    topic: str
    messages: list[Message]


class SessionEndResponse(BaseModel):
    session_id: str
    title: str
    summary: str
    skill_update: dict


@router.post("/session/end", response_model=SessionEndResponse)
async def end_session(req: SessionEndRequest):
    transcript = "\n".join(f"{m.role.upper()}: {m.content}" for m in req.messages)

    response = await claude._client.messages.create(
        model=claude.HAIKU,
        max_tokens=1024,
        tools=[_SUMMARISE_TOOL],
        tool_choice={"type": "tool", "name": "save_session_summary"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarise this learning session on '{req.topic}'.\n\n"
                    f"<transcript>\n{transcript}\n</transcript>"
                ),
            }
        ],
    )

    summary_data: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "save_session_summary":
            summary_data = block.input
            break

    title = summary_data.get("title", f"Session on {req.topic}")
    narrative = summary_data.get("narrative_summary", "")
    skill_update = summary_data.get("skill_update", {})

    entry = EpisodicEntry(
        topic=req.topic,
        topic_category=req.topic,
        type="session",
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        title=title,
        summary=narrative,
    )
    result = await save_session(req.user_id, entry)
    session_id = result["session_id"]

    if skill_update.get("current_level"):
        try:
            upsert_skill(
                req.user_id,
                req.topic,
                SkillUpdate(
                    current_level=skill_update.get("current_level"),
                    signals={
                        "weak_areas": skill_update.get("weak_areas", []),
                        "strong_areas": skill_update.get("strong_areas", []),
                    },
                ),
            )
        except Exception as e:
            logger.warning("Skill graph merge failed: %s", e)

    return SessionEndResponse(
        session_id=session_id,
        title=title,
        summary=narrative,
        skill_update=skill_update,
    )
