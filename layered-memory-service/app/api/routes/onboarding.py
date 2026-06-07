import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import verify_api_key
from app.memory.l2.crud import upsert_skill
from app.models.l2 import SkillUpdate
from app.services import claude

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Onboarding"], dependencies=[Depends(verify_api_key)])

_LEVELS = ["beginner", "intermediate", "advanced", "expert"]

_GOAL_KB: dict[str, list[dict]] = {
    "data science": [
        {"topic": "Python", "required_level": "intermediate"},
        {"topic": "Statistics", "required_level": "intermediate"},
        {"topic": "Machine Learning", "required_level": "intermediate"},
        {"topic": "Data Wrangling", "required_level": "intermediate"},
        {"topic": "SQL", "required_level": "beginner"},
    ],
    "web development": [
        {"topic": "HTML & CSS", "required_level": "intermediate"},
        {"topic": "JavaScript", "required_level": "intermediate"},
        {"topic": "React", "required_level": "intermediate"},
        {"topic": "Node.js", "required_level": "beginner"},
        {"topic": "REST APIs", "required_level": "beginner"},
    ],
    "backend development": [
        {"topic": "Python", "required_level": "intermediate"},
        {"topic": "FastAPI", "required_level": "intermediate"},
        {"topic": "Databases", "required_level": "intermediate"},
        {"topic": "REST APIs", "required_level": "intermediate"},
        {"topic": "System Design", "required_level": "beginner"},
    ],
    "machine learning": [
        {"topic": "Python", "required_level": "intermediate"},
        {"topic": "Linear Algebra", "required_level": "intermediate"},
        {"topic": "Statistics", "required_level": "intermediate"},
        {"topic": "Machine Learning", "required_level": "advanced"},
        {"topic": "Deep Learning", "required_level": "intermediate"},
    ],
    "devops": [
        {"topic": "Linux", "required_level": "intermediate"},
        {"topic": "Docker", "required_level": "intermediate"},
        {"topic": "CI/CD", "required_level": "intermediate"},
        {"topic": "Kubernetes", "required_level": "beginner"},
        {"topic": "Cloud", "required_level": "beginner"},
    ],
}

_DERIVE_TOPICS_TOOL = {
    "name": "create_skill_topics",
    "description": "Return a list of skill topics needed for the given learning goal.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "required_level": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced", "expert"],
                        },
                    },
                    "required": ["topic", "required_level"],
                },
            }
        },
        "required": ["topics"],
    },
}


def _gap(required: str, current: str = "beginner") -> str:
    r = _LEVELS.index(required) if required in _LEVELS else 1
    c = _LEVELS.index(current) if current in _LEVELS else 0
    diff = r - c
    if diff <= 0:
        return "none"
    if diff == 1:
        return "small"
    if diff == 2:
        return "medium"
    return "large"


def _kb_lookup(goal: str) -> list[dict] | None:
    lower = goal.lower()
    for key, topics in _GOAL_KB.items():
        if key in lower:
            return topics
    return None


async def _haiku_derive(goal: str) -> list[dict]:
    response = await claude._client.messages.create(
        model=claude.HAIKU,
        max_tokens=512,
        tools=[_DERIVE_TOPICS_TOOL],
        tool_choice={"type": "tool", "name": "create_skill_topics"},
        messages=[
            {
                "role": "user",
                "content": f"What are the key skill topics someone needs to learn to achieve this goal: '{goal}'? List 4-6 topics with their required level.",
            }
        ],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_skill_topics":
            return block.input.get("topics", [])
    return []


class BootstrapRequest(BaseModel):
    user_id: str
    goal: str
    current_level: str = "beginner"


class BootstrapResponse(BaseModel):
    topics: list[dict]


@router.post("/onboarding/bootstrap", response_model=BootstrapResponse)
async def bootstrap(req: BootstrapRequest):
    raw_topics = _kb_lookup(req.goal) or await _haiku_derive(req.goal)

    created = []
    for t in raw_topics:
        topic = t["topic"]
        required_level = t["required_level"]
        gap = _gap(required_level, req.current_level)
        try:
            upsert_skill(
                req.user_id,
                topic,
                SkillUpdate(
                    required_level=required_level,
                    current_level=req.current_level,
                    gap=gap,
                ),
            )
            created.append({"topic": topic, "required_level": required_level, "gap": gap})
        except Exception as e:
            logger.warning("Failed to upsert skill %s: %s", topic, e)

    return BootstrapResponse(topics=created)
