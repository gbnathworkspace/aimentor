"""classify_fact_quality — judges whether each "Facts About You" entry
actually states a fact about the user, or just names a topic/skill.

Same call shape as l1_scope.classify_relevance (Haiku, structured output,
position-paired so the model's echoed text is never trusted) but a
different question: not "is this relevant to a topic" but "does this say
something about the user".
"""

import hashlib
import json
import logging

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def compute_situations_stamp(situations: list[str]) -> str:
    """Stable hash of the situations list — lets the caller (see
    routers/profile.py) skip the LLM call when nothing changed since the
    last judgment, same pattern as l1_scope.compute_profile_stamp."""
    payload = json.dumps({"situations": situations}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class _FactJudgment(BaseModel):
    is_fact: bool
    reason: str
    # Only meaningful when is_fact=false — a first-person rewrite of the
    # same content ("Cloud architecture (AWS)" -> "I have experience with
    # cloud architecture (AWS)"), never invents new information.
    rewrite: str | None = None


class _FactJudgments(BaseModel):
    judgments: list[_FactJudgment]


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i + 1}. {text}" for i, text in enumerate(items)) or "(none)"


async def classify_fact_quality(texts: list[str]) -> list[dict]:
    """One shared Haiku call judging whether each text is a real fact about
    the user (something true about them — role, experience, constraint,
    preference, or a genuinely stated interest/goal) versus a bare
    topic/skill name with no personal framing at all.

    Returns [{"text": str, "is_fact": bool, "reason": str}, ...], one entry
    per input, same order. Returns [] immediately, no LLM call, if empty.

    Raises ValueError if the model returns a different number of judgments
    than items given, rather than silently pairing mismatched positions.
    """
    if not texts:
        return []

    llm = ChatAnthropic(
        model=HAIKU_MODEL, api_key=get_settings().ANTHROPIC_API_KEY,
    ).with_structured_output(_FactJudgments)

    prompt = (
        "Each numbered item below is something a user entered under "
        '"Facts About You" in a learning-mentor app. A good fact is a '
        "first-person statement that is TRUE ABOUT THE USER — their role, "
        "experience, constraints, preferences, OR a genuinely stated "
        "interest/goal (e.g. \"I'm a backend engineer\", \"I have 5 years "
        'of Python experience\", "I\'m interested in learning React", "I '
        'want to switch into ML"). A stated interest counts as a real '
        "fact — it IS true that the user is interested, even though it "
        "isn't evidence of skill. A bad entry is a BARE topic or skill "
        'name with no personal framing at all (e.g. "Cloud architecture", '
        '"AI/ML integration", "Database optimization") — it says nothing '
        "about the user, just names a subject.\n\n"
        "Judge each item true (is_fact=true — has personal framing, even "
        "if it's just \"I'm interested in X\") or false (is_fact=false — "
        "a bare topic/skill name, no reference to the user at all).\n\n"
        "When is_fact is false, also set rewrite to a first-person version "
        "that turns the same content into a real fact about the user — "
        'e.g. "Cloud architecture (AWS, Docker, microservices)" becomes '
        '"I have experience with cloud architecture (AWS, Docker, '
        'microservices)". Never invent specifics (years, seniority, '
        "projects) that aren't in the original text — only reframe it as "
        "something about the user. Leave rewrite unset when is_fact is "
        "true.\n\n"
        f"Items ({len(texts)}):\n{_numbered(texts)}\n\n"
        f"Return exactly {len(texts)} judgments, one per item, same order."
    )
    result = await llm.ainvoke(prompt)

    if len(result.judgments) != len(texts):
        raise ValueError(
            f"classify_fact_quality count mismatch: {len(result.judgments)}/{len(texts)}"
        )

    out = []
    for text, j in zip(texts, result.judgments):
        is_fact, rewrite = j.is_fact, j.rewrite
        # A rewrite that doesn't actually change anything is a dead end for
        # the UI's "Rewrite as a fact" button — clicking it would be a
        # no-op and the warning could never clear. If the model couldn't
        # produce a meaningfully different rewrite, treat the text as
        # already as good as it can get rather than flagging it forever.
        if not is_fact and (not rewrite or rewrite.strip().lower() == text.strip().lower()):
            is_fact, rewrite = True, None
        out.append({"text": text, "is_fact": is_fact, "reason": j.reason, "rewrite": rewrite})
    return out
