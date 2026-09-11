"""orchestrator — the single entry point every user message passes through.
Decides which specialist agent handles a message; never does the work
itself (no tools, no DB writes, no answering).

Gate (plain Python, no LLM call): a message that already belongs to an
open topic thread always goes to tutoring_agent — there's nothing to
route, and command_agent is only reachable from a topic-less message
(welcome screen) or a dedicated UI action, never from inside a chat.
Only once there's no topic_id does the model get a real choice to make,
mirroring mode_router.py's Rule 1 cold-start gate.

Fail-open convention, matching mode_router.py/topic_router.py: any
failure (timeout, API error, malformed response, or a genuinely
unclassifiable query) falls back to tutoring_agent — most messages are
teaching-related, and it can still hold a normal conversation even off an
uncertain classification.
"""

import asyncio
import logging
from enum import Enum

import anthropic
from pydantic import BaseModel, ValidationError

from app.config.settings import get_settings
from app.services.llm_trace import traced_messages_create

logger = logging.getLogger(__name__)

_ORCHESTRATOR_MODEL = "claude-haiku-4-5-20251001"
_ORCHESTRATOR_TIMEOUT_SECONDS = 5
_ORCHESTRATOR_MAX_TOKENS = 300


class AgentName(str, Enum):
    TUTORING = "tutoring_agent"
    TOPIC_ASSIGNMENT = "topic_assignment_agent"
    COMMAND = "command_agent"


class MatchedRule(str, Enum):
    RULE_1_OPEN_TOPIC_GATE = "RULE_1_OPEN_TOPIC_GATE"
    RULE_2_MODEL_DISPATCH = "RULE_2_MODEL_DISPATCH"
    RULE_3_FALLBACK = "RULE_3_FALLBACK"


class OrchestratorDecision(BaseModel):
    matched_rule: MatchedRule
    agent: AgentName
    reasoning: str = ""


_FALLBACK_DECISION = OrchestratorDecision(
    matched_rule=MatchedRule.RULE_3_FALLBACK,
    agent=AgentName.TUTORING,
    reasoning="Orchestrator call failed, timed out, or was unclassifiable — defaulted to tutoring_agent.",
)

_AGENT_REGISTRY = {
    AgentName.TUTORING: (
        "Handles learning/teaching conversations - explaining topics, "
        "answering questions, diagnosing skill level, continuing a study "
        "session."
    ),
    AgentName.TOPIC_ASSIGNMENT: (
        "Decides which existing topic a brand-new message continues, or "
        "whether it starts a new topic. Only for messages with no open "
        "topic yet."
    ),
    AgentName.COMMAND: (
        "Handles account/topic management actions typed as text - archive "
        "or rename a topic. Not for anything about topic content."
    ),
}

_TOOL_SCHEMA = {
    "name": "select_agent",
    "description": "Selects which agent should handle this user message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "enum": [a.value for a in AgentName],
                "description": "The single agent that should handle this message.",
            },
            "reasoning": {"type": "string", "description": "One sentence why."},
        },
        "required": ["agent", "reasoning"],
    },
}

_SYSTEM_PROMPT = (
    "You are the orchestrator for an AI mentor app. This message has no "
    "open topic yet. Pick exactly one agent to handle it from this "
    "registry:\n\n"
    + "\n".join(f"- {name.value}: {desc}" for name, desc in _AGENT_REGISTRY.items())
    + "\n\nCall select_agent with your choice. Prefer tutoring_agent unless "
    "the message is clearly a topic-continuation question or an explicit "
    "archive/rename request."
)


async def route_message(query: str) -> OrchestratorDecision:
    """Decide which agent handles `query`.

    Call this ONLY for messages with no topic_id (e.g. the welcome
    screen). A message already inside an open topic thread must skip
    this function entirely and dispatch straight to tutoring_agent —
    that gate lives in the caller, not here, since it needs no query
    content to decide.
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await asyncio.wait_for(
            traced_messages_create(
                client, call_site="orchestrator.route_message",
                model=_ORCHESTRATOR_MODEL,
                max_tokens=_ORCHESTRATOR_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "select_agent"},
                messages=[{"role": "user", "content": query}],
            ),
            timeout=_ORCHESTRATOR_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Orchestrator timed out after %ds — defaulting to tutoring_agent.", _ORCHESTRATOR_TIMEOUT_SECONDS)
        return _FALLBACK_DECISION
    except Exception as e:
        logger.warning("Orchestrator call failed: %s — defaulting to tutoring_agent.", e)
        return _FALLBACK_DECISION

    try:
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return OrchestratorDecision(matched_rule=MatchedRule.RULE_2_MODEL_DISPATCH, **tool_use.input)
    except (StopIteration, ValidationError, TypeError) as e:
        logger.warning("Orchestrator returned an unusable response: %s — defaulting to tutoring_agent.", e)
        return _FALLBACK_DECISION


def route(query: str, topic_id: str | None) -> OrchestratorDecision | None:
    """Rule 1: the open-topic gate. Returns a decision immediately, no
    LLM call, when `topic_id` is set. Returns None when the caller must
    await route_message(query) instead."""
    if topic_id:
        return OrchestratorDecision(
            matched_rule=MatchedRule.RULE_1_OPEN_TOPIC_GATE,
            agent=AgentName.TUTORING,
            reasoning="Message belongs to an already-open topic thread.",
        )
    return None
