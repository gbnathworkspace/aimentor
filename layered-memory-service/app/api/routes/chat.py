import logging
import pathlib
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import verify_api_key
from app.memory.l2.crud import upsert_skill
from app.models.l2 import SkillUpdate
from app.services import claude, context as ctx

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"], dependencies=[Depends(verify_api_key)])

_PROMPT_DIR = pathlib.Path(__file__).parents[3] / "prompts"

_UPDATE_SKILL_TOOL = {
    "name": "update_skill_graph",
    "description": "Record your honest assessment of the learner's current skill level after evaluation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "current_level": {"type": "string", "enum": ["beginner", "intermediate", "advanced", "expert"]},
            "gap": {"type": "string", "enum": ["none", "small", "medium", "large"]},
            "weak_areas": {"type": "array", "items": {"type": "string"}},
            "strong_areas": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["current_level", "gap"],
    },
}


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    user_id: str
    topic: str
    mode: Literal["learning", "evaluation", "practice"] = "learning"
    tone: str = "encouraging"
    messages: list[Message]


class ChatResponse(BaseModel):
    text: str


def _load_prompt(version: int = 1) -> str:
    return (_PROMPT_DIR / f"mentor_v{version}.md").read_text()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    last_user_msg = next(
        (m.content for m in reversed(req.messages) if m.role == "user"),
        req.topic,
    )
    context = await ctx.assemble(req.user_id, req.topic, last_user_msg)

    profile = context["profile"]
    skill = context["skill"]
    episodes = context["episodes"]

    episode_text = "\n".join(
        f"- [{e.get('date', '')}] {e.get('title', '')}: {e.get('summary', '')}"
        for e in episodes
    ) or "No previous sessions."

    system = _load_prompt().format(
        goal=profile.get("goal", "Not set"),
        overall_level=profile.get("overall_level", "Unknown"),
        daily_availability=profile.get("daily_availability", "Unknown"),
        deadline=profile.get("deadline", "Not set"),
        topic=req.topic,
        required_level=skill.get("required_level", "Unknown"),
        current_level=skill.get("current_level", "Unknown"),
        gap=skill.get("gap", "Unknown"),
        episodes=episode_text,
        mode=req.mode,
        tone=req.tone,
    )

    kwargs: dict = {
        "model": claude.SONNET,
        "max_tokens": 2048,
        "system": system,
        "messages": [m.model_dump() for m in req.messages],
    }
    if req.mode == "evaluation":
        kwargs["tools"] = [_UPDATE_SKILL_TOOL]

    response = await claude._client.messages.create(**kwargs)

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use" and block.name == "update_skill_graph":
            _apply_skill_update(req.user_id, req.topic, block.input)

    return ChatResponse(text=text)


def _apply_skill_update(user_id: str, topic: str, data: dict) -> None:
    try:
        upsert_skill(
            user_id,
            topic,
            SkillUpdate(
                current_level=data.get("current_level"),
                gap=data.get("gap"),
                signals={
                    "weak_areas": data.get("weak_areas", []),
                    "strong_areas": data.get("strong_areas", []),
                },
            ),
        )
    except Exception as e:
        logger.warning("Skill graph update failed: %s", e)
