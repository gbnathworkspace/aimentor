"""Pre-turn mode routing for topic-mode mentor turns.

Decides which teaching tactic the mentor should use for this turn —
DIAGNOSTIC / DIRECT / SOCRATIC / HINT / GUIDED — instead of leaving that
decision to a single static prompt that used to give the model
contradictory instructions ("probe first" vs "explain first" vs
"attempt-first", all in one block, no priority order).

Rule 1 (cold start) is a plain Python check, not an LLM call — it only
depends on the skill graph's `assessed` flag. Rules 2-6 are a forced
tool_use call to Haiku, only spent once a topic has a real assessment.
"""

import asyncio
import logging
from enum import Enum
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_ROUTER_MODEL = "claude-haiku-4-5-20251001"
_ROUTER_TIMEOUT_SECONDS = 5
_ROUTER_MAX_TOKENS = 300
_RECENT_MESSAGE_WINDOW = 6
"""How many recent turns the router reads to judge frustration/attempts."""


class MentorMode(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    DIRECT = "DIRECT"
    SOCRATIC = "SOCRATIC"
    HINT = "HINT"
    GUIDED = "GUIDED"


class MatchedRule(str, Enum):
    RULE_1_COLD_START = "RULE_1_COLD_START"
    RULE_2_URGENCY_DIRECT = "RULE_2_URGENCY_DIRECT"
    RULE_3_HIGH_FRUSTRATION_MULTI_ERROR = "RULE_3_HIGH_FRUSTRATION_MULTI_ERROR"
    RULE_4_SINGLE_ERROR_HINT = "RULE_4_SINGLE_ERROR_HINT"
    RULE_5_ZERO_ATTEMPT_SOCRATIC = "RULE_5_ZERO_ATTEMPT_SOCRATIC"
    RULE_6_CATCH_ALL_FALLBACK = "RULE_6_CATCH_ALL_FALLBACK"


class RouterDecision(BaseModel):
    matched_rule: MatchedRule
    selected_mode: MentorMode
    reasoning: str
    # Specific instruction spliced into the mentor's system prompt for this
    # turn — lets the router hand down a targeted directive instead of the
    # mentor re-deriving "why" from the mode name alone. Optional: the
    # mode's own static instructions are often enough on their own.
    instruction_override: str = ""


_FALLBACK_DECISION = RouterDecision(
    matched_rule=MatchedRule.RULE_6_CATCH_ALL_FALLBACK,
    selected_mode=MentorMode.SOCRATIC,
    reasoning="Router call failed or timed out — defaulted to attempt-first.",
)

_ROUTER_TOOL_SCHEMA = {
    "name": "select_mentor_mode",
    "description": (
        "Selects the exact teaching mode for the mentor's next response by "
        "evaluating a strict top-down decision tree."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "matched_rule": {
                "type": "string",
                "enum": [r.value for r in MatchedRule],
                "description": "The top-most rule that evaluated to true.",
            },
            "selected_mode": {
                "type": "string",
                "enum": [m.value for m in MentorMode],
                "description": "The mentor mode corresponding to the matched rule.",
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences on why this rule matched first.",
            },
            "instruction_override": {
                "type": "string",
                "description": (
                    "Optional specific instruction for the mentor's next reply "
                    "(e.g. 'the user tried twice and got a null pointer both "
                    "times — de-escalate and walk step 1 only'). Empty string "
                    "if the mode's own default instructions are sufficient."
                ),
            },
        },
        "required": ["matched_rule", "selected_mode", "reasoning"],
    },
}

_ROUTER_SYSTEM_PROMPT = """You are the Mode Routing Engine for an AI mentor. Your sole job is to select the exact teaching mode for the mentor's next response by evaluating rules strictly top-to-bottom and stopping at the first match. Do not evaluate rules after a match is found.

RULE 2 — URGENCY / DIRECT LOOKUP
  User explicitly asks for a direct answer ("just tell me", "give me the code"), or asks a pure factual/syntax lookup ("what port does HTTPS use?", "syntax for array push").
  -> RULE_2_URGENCY_DIRECT / DIRECT

RULE 3 — HIGH FRUSTRATION / MULTI-ERROR
  Recent turns show 2+ consecutive failed attempts on the same problem, OR clear frustration language ("I'm lost", "tried everything", "nothing works"), OR a multi-step task the user explicitly says they don't know where to start on.
  -> RULE_3_HIGH_FRUSTRATION_MULTI_ERROR / GUIDED

RULE 4 — SINGLE ERROR / SPECIFIC BLIND SPOT
  User made one attempt (shared code/an approach) and hit a specific, targeted point of confusion — not yet frustrated, not a repeated failure.
  -> RULE_4_SINGLE_ERROR_HINT / HINT

RULE 5 — ZERO ATTEMPT
  User asks a broad conceptual or multi-step question with no attempt, code, or effort shown yet, and no error history.
  -> RULE_5_ZERO_ATTEMPT_SOCRATIC / SOCRATIC

RULE 6 — CATCH-ALL
  None of the above matched cleanly.
  -> RULE_6_CATCH_ALL_FALLBACK / SOCRATIC

(Rule 1, the cold-start/diagnostic gate, is evaluated in code before you're called — you will never be asked to route a turn that needs it.)

Call select_mentor_mode with your decision. Keep reasoning short."""


def _format_recent_messages(messages: list[dict], window: int) -> str:
    recent = [m for m in messages if m.get("type") == "message"][-window:]
    lines = [f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}" for m in recent]
    return "\n\n".join(lines) if lines else "(no prior messages this topic)"


async def route_user_turn(
    query: str,
    skill: dict[str, Any],
    recent_messages: list[dict],
) -> RouterDecision:
    """Decide the mentor mode for this turn.

    Rule 1 (cold start) is a plain Python check — no LLM call spent while
    the topic has never been assessed. Rules 2-6 run a forced tool_use
    call to Haiku once there's an actual level to route around.

    Never raises — falls back to SOCRATIC on any failure, matching the
    fail-open pattern used throughout context_assembler.py.
    """
    if not skill.get("assessed"):
        return RouterDecision(
            matched_rule=MatchedRule.RULE_1_COLD_START,
            selected_mode=MentorMode.DIAGNOSTIC,
            reasoning="Topic has no verified skill assessment yet.",
        )

    user_payload = (
        f"User query: {query!r}\n\n"
        f"Skill state: current_level={skill.get('current_level')}, "
        f"required_level={skill.get('required_level')}, gap={skill.get('gap')}\n\n"
        f"Recent turns in this topic:\n{_format_recent_messages(recent_messages, _RECENT_MESSAGE_WINDOW)}"
    )

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=_ROUTER_MODEL,
                max_tokens=_ROUTER_MAX_TOKENS,
                system=_ROUTER_SYSTEM_PROMPT,
                tools=[_ROUTER_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "select_mentor_mode"},
                messages=[{"role": "user", "content": user_payload}],
            ),
            timeout=_ROUTER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Mode router timed out after %ds — defaulting to SOCRATIC.", _ROUTER_TIMEOUT_SECONDS)
        return _FALLBACK_DECISION
    except Exception as e:
        logger.warning("Mode router call failed: %s — defaulting to SOCRATIC.", e)
        return _FALLBACK_DECISION

    try:
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return RouterDecision(**tool_use.input)
    except (StopIteration, ValidationError, TypeError) as e:
        logger.warning("Mode router returned an unusable response: %s — defaulting to SOCRATIC.", e)
        return _FALLBACK_DECISION
