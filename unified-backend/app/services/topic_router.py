"""topic_router — decides which existing topic (if any) a new welcome-screen
message continues, replacing the old client-side keyword-overlap heuristic
(mentorman-web's former detectTopic.ts) with a semantic judgment call.

A wrong guess here costs nothing but a re-pick — the frontend always shows
the pick as a "Sounds like X — continue / start new / pick different" dialog
(or, when ambiguous, a short pick-list) the user confirms or overrides,
never a silent reroute. That's what makes a single unverified Haiku call an
acceptable trade here (unlike e.g. mentor prompt content, which the user
never gets a chance to veto turn-by-turn).

Same fail-open convention as mode_router.py: any failure (timeout, API
error, malformed response) falls back to TopicRouteResult() (no match, no
candidates), i.e. "start a new topic" — the safe default the UI already
falls back to when nothing matches.
"""

import asyncio
import logging
from typing import Any

import anthropic
from pydantic import BaseModel, Field, ValidationError

from app.config.settings import get_settings
from app.services.llm_trace import traced_messages_create

logger = logging.getLogger(__name__)

_ROUTER_MODEL = "claude-haiku-4-5-20251001"
_ROUTER_TIMEOUT_SECONDS = 5
_ROUTER_MAX_TOKENS = 300
_MAX_RELATED = 4

_SYSTEM_PROMPT = (
    "You route a new chat message to the existing topic thread it continues, "
    "or flag it as the start of something new. Match on subject matter, not "
    "surface wording — \"explain hooks\" continues a \"React\" topic even "
    "without the word React appearing.\n\n"
    "Decide exactly one of three outcomes:\n"
    "- MATCH: one existing topic is clearly what this continues. Call "
    "topic_id with its id.\n"
    "- AMBIGUOUS: several existing topics could plausibly be it and you "
    "can't confidently pick just one. Call related_ids with up to 4 "
    "candidate ids, most-likely first. Only use this when there's genuine "
    "overlap worth surfacing — don't pad it with topics that aren't "
    "actually related just to fill it out.\n"
    "- NEW: nothing existing is a plausible continuation.\n\n"
    "A wrong pick here just costs the user a re-pick, so don't force a "
    "MATCH or AMBIGUOUS call that isn't really there — prefer NEW over "
    "guessing."
)


class _TopicRouteDecision(BaseModel):
    decision: str
    topic_id: str | None = None
    related_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""


class TopicRouteResult(BaseModel):
    """topic_id set = confident single match. related_ids (up to 4) set =
    ambiguous, let the user pick. Both empty/None = start a new topic
    (the model's genuine NEW call, or any router failure — same outcome)."""

    topic_id: str | None = None
    related_ids: list[str] = Field(default_factory=list)


def _tool_schema(topic_ids: list[str]) -> dict[str, Any]:
    return {
        "name": "select_topic",
        "description": (
            "Selects which existing topic (by id) this message continues, "
            "flags it as ambiguous between a few candidates, or NEW if none fit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["MATCH", "AMBIGUOUS", "NEW"],
                    "description": "MATCH: one topic clearly fits, call topic_id. AMBIGUOUS: a few could fit, call related_ids. NEW: none fit.",
                },
                "topic_id": {
                    "type": "string",
                    "enum": topic_ids,
                    "description": "Required when decision=MATCH: the single topic this message continues.",
                },
                "related_ids": {
                    "type": "array",
                    "items": {"type": "string", "enum": topic_ids},
                    "maxItems": _MAX_RELATED,
                    "description": "Required when decision=AMBIGUOUS: up to 4 candidate topics, most-likely first.",
                },
                "reasoning": {"type": "string", "description": "One sentence on why."},
            },
            "required": ["decision", "reasoning"],
        },
    }


def _format_topics(topics: list[dict]) -> str:
    lines = []
    for t in topics:
        subject = f" ({t['subject']})" if t.get("subject") else ""
        lines.append(f"- id={t['topicId']}: {t['title']}{subject}")
    return "\n".join(lines)


async def route_topic(query: str, topics: list[dict]) -> TopicRouteResult:
    """Decide whether `query` continues one existing topic (MATCH), could
    plausibly continue a few (AMBIGUOUS — up to 4 candidates, ranked), or
    should start a new one (NEW, or any router failure — same outcome).

    Returns an empty TopicRouteResult immediately, no LLM call, when there
    are no candidate topics to route against.
    """
    if not topics:
        return TopicRouteResult()

    topic_ids = [t["topicId"] for t in topics]
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await asyncio.wait_for(
            traced_messages_create(
                client, call_site="topic_router.route_topic",
                model=_ROUTER_MODEL,
                max_tokens=_ROUTER_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[_tool_schema(topic_ids)],
                tool_choice={"type": "tool", "name": "select_topic"},
                messages=[{
                    "role": "user",
                    "content": f"Message: {query!r}\n\nExisting topics:\n{_format_topics(topics)}",
                }],
            ),
            timeout=_ROUTER_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Topic router timed out after %ds — defaulting to NEW.", _ROUTER_TIMEOUT_SECONDS)
        return TopicRouteResult()
    except Exception as e:
        logger.warning("Topic router call failed: %s — defaulting to NEW.", e)
        return TopicRouteResult()

    try:
        tool_use = next(b for b in response.content if b.type == "tool_use")
        decision = _TopicRouteDecision(**tool_use.input)
    except (StopIteration, ValidationError, TypeError) as e:
        logger.warning("Topic router returned an unusable response: %s — defaulting to NEW.", e)
        return TopicRouteResult()

    if decision.decision == "MATCH" and decision.topic_id in topic_ids:
        return TopicRouteResult(topic_id=decision.topic_id)

    if decision.decision == "AMBIGUOUS":
        related = [tid for tid in decision.related_ids if tid in topic_ids][:_MAX_RELATED]
        if related:
            return TopicRouteResult(related_ids=related)

    # NEW, or a malformed/unusable MATCH or AMBIGUOUS call — same safe default.
    return TopicRouteResult()
