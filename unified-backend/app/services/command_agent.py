"""command_agent — resolves non-teaching account/topic actions ("archive my
python topic", "rename this to X") to a specific topic + action, and
executes them via TopicService.

Same fail-open convention as mode_router.py/topic_router.py for the
*resolve* step (any failure -> NONE, no guess). Resolve and execute are
kept separate so the caller can show a confirm step before calling
execute() if it wants one (topic_router.py's MATCH/AMBIGUOUS dialog is the
existing precedent for not auto-acting on a single unverified Haiku call).
"""

import asyncio
import logging
from enum import Enum
from typing import Any

import anthropic
from pydantic import BaseModel, Field, ValidationError

from app.config.settings import get_settings
from app.services.llm_trace import traced_messages_create
from app.services.topic_service import TopicService

logger = logging.getLogger(__name__)

_AGENT_MODEL = "claude-haiku-4-5-20251001"
_AGENT_TIMEOUT_SECONDS = 5
_AGENT_MAX_TOKENS = 300

_topic_service = TopicService()


class CommandAction(str, Enum):
    ARCHIVE = "ARCHIVE"
    RENAME = "RENAME"
    NONE = "NONE"


class CommandDecision(BaseModel):
    action: CommandAction
    topic_id: str | None = None
    new_title: str | None = None
    reasoning: str = ""


_FALLBACK_DECISION = CommandDecision(
    action=CommandAction.NONE,
    reasoning="Router call failed, timed out, or no confident topic match — no action taken.",
)


def _tool_schema(topic_ids: list[str]) -> dict[str, Any]:
    return {
        "name": "select_command",
        "description": (
            "Selects which action to take on which topic, or NONE if the "
            "message doesn't clearly name one existing topic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [a.value for a in CommandAction],
                    "description": (
                        "ARCHIVE/RENAME require topic_id. NONE if no "
                        "single topic is a confident match — never guess."
                    ),
                },
                "topic_id": {
                    "type": "string",
                    "enum": topic_ids,
                    "description": "Required for ARCHIVE/RENAME.",
                },
                "new_title": {
                    "type": "string",
                    "description": "Required for RENAME: the new title.",
                },
                "reasoning": {"type": "string", "description": "One sentence why."},
            },
            "required": ["action", "reasoning"],
        },
    }


_SYSTEM_PROMPT = (
    "You resolve a user's account-management request to one action on one "
    "existing topic. Match on subject matter, not exact wording.\n\n"
    "- ARCHIVE: user wants a topic put away/hidden, not deleted "
    "(\"archive\", \"put away\", \"I'm done with this for now\").\n"
    "- RENAME: user wants a topic's title changed — call new_title with the "
    "new title.\n"
    "- NONE: the message doesn't clearly name exactly one existing topic, or "
    "isn't actually an account-management request. Prefer NONE over "
    "guessing — a wrong ARCHIVE/RENAME is costly, unlike routing."
)


def _format_topics(topics: list[dict]) -> str:
    return "\n".join(f"- id={t['topicId']}: {t['title']}" for t in topics)


async def resolve_command(query: str, topics: list[dict]) -> CommandDecision:
    """Classify `query` into an action + target topic. No side effects.

    Returns NONE immediately, no LLM call, when the user has no topics to
    act on.
    """
    if not topics:
        return CommandDecision(action=CommandAction.NONE, reasoning="User has no topics.")

    topic_ids = [t["topicId"] for t in topics]
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await asyncio.wait_for(
            traced_messages_create(
                client, call_site="command_agent.resolve_command",
                model=_AGENT_MODEL,
                max_tokens=_AGENT_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[_tool_schema(topic_ids)],
                tool_choice={"type": "tool", "name": "select_command"},
                messages=[{
                    "role": "user",
                    "content": f"Message: {query!r}\n\nExisting topics:\n{_format_topics(topics)}",
                }],
            ),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("command_agent timed out after %ds", _AGENT_TIMEOUT_SECONDS)
        return _FALLBACK_DECISION
    except Exception as e:
        logger.warning("command_agent call failed: %s", e)
        return _FALLBACK_DECISION

    try:
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return CommandDecision(**tool_use.input)
    except (StopIteration, ValidationError, TypeError) as e:
        logger.warning("command_agent returned an unusable response: %s", e)
        return _FALLBACK_DECISION


async def execute_command(decision: CommandDecision, user_id: str) -> dict:
    """Apply a resolved decision. Performs the action unconditionally —
    caller's job to confirm with the user first if it wants to."""
    if decision.action == CommandAction.NONE or not decision.topic_id:
        return {"status": "no_action", "reasoning": decision.reasoning}

    if decision.action == CommandAction.ARCHIVE:
        await _topic_service.archive_topic(decision.topic_id, user_id)
        return {"status": "archived", "topic_id": decision.topic_id}

    if decision.action == CommandAction.RENAME:
        if not decision.new_title:
            return {"status": "no_action", "reasoning": "RENAME with no new_title."}
        updated = await _topic_service.update_topic(decision.topic_id, user_id, title=decision.new_title)
        return {"status": "renamed", "topic_id": decision.topic_id, "title": updated["title"]}

    return {"status": "no_action", "reasoning": decision.reasoning}
