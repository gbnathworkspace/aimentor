"""classify_relevance — judges L1 situations (facts about the user) against
a topic.

Used to compute `l1_scope`, cached on the topic document (see
TopicService._ensure_l1_scope), so mentor prompts inject only the facts
relevant to the topic being discussed instead of flattening the user's full
profile list into every turn — and so SubtopicWeightsModal's goal-picker
only offers facts that actually overlap the topic being weighted (see
.kiro/specs/topic-scoping).
"""

import hashlib
import json
import logging
from typing import Literal

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"

Verdict = Literal["relevant", "irrelevant", "uncertain"]


class _Judgment(BaseModel):
    """One position's verdict. No text field — the model is never trusted
    to echo the original string back; classify_relevance() substitutes the
    real text in by position instead, so a paraphrase or whitespace drift
    in the model's output can never silently drop a relevant item.

    `verdict` is a real three-way label, not a bool with a bias baked in —
    "uncertain" is a genuine, distinct outcome from "relevant", not a
    forced pick between the two. What to DO with "uncertain" (include it
    or not) is a policy decision made once, downstream, in
    classify_relevance's return value — not smuggled into what the model
    is asked to report."""

    verdict: Verdict
    reason: str


class _RelevanceJudgments(BaseModel):
    """Position-aligned to the input list, not keyed by re-echoed text."""

    situation_judgments: list[_Judgment]


def extract_situations(profile: dict) -> list[str]:
    """Pull the full "Facts About You" list out of a profile doc — folding
    in `label` so every reader (classify_relevance's input, prompt_store's
    fallback) uses one definition instead of several that can drift apart.
    There is no separate `contexts` field any more — a stray, UI-less
    duplicate of this same list that used to confuse per-topic memory
    views."""
    detail = profile.get("learning_context_detail") or {}
    situations = list(detail.get("situations") or [])

    label = detail.get("label")
    if label and label not in situations:
        situations.insert(0, label)

    return situations


def compute_profile_stamp(situations: list[str]) -> str:
    """Stable hash of the situations list — cheap equality check for
    staleness, no TTL, no invalidation logic."""
    payload = json.dumps({"situations": situations}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i + 1}. {text}" for i, text in enumerate(items)) or "(none)"


async def classify_relevance(topic: str, situations: list[str]) -> list[dict]:
    """One shared Haiku call judging every fact against `topic`.

    Returns [{"situation": str, "verdict": "relevant"|"irrelevant"|"uncertain",
    "reason": str}, ...], one entry per input item, same order. Returns []
    immediately, no LLM call, if the list is empty.

    Raises ValueError if the model returns a different number of judgments
    than items given, rather than silently pairing mismatched positions.
    """
    if not situations:
        return []

    llm = ChatAnthropic(
        model=HAIKU_MODEL, api_key=get_settings().ANTHROPIC_API_KEY,
    ).with_structured_output(_RelevanceJudgments)

    prompt = (
        f"Topic: {topic}\n\n"
        "For each numbered item below, judge whether it changes what matters "
        f"for discussing/teaching **{topic}** — topical connection only. "
        "Ignore how urgent or casual the phrasing sounds; that reflects the "
        "user's tone, not the item's relevance to this topic.\n\n"
        "Judge each item 'relevant', 'irrelevant', or 'uncertain'. Use "
        "'uncertain' only when you genuinely cannot tell from the text alone "
        "— don't guess just to avoid it, and don't use it as a default when "
        "you actually do have a read either way.\n\n"
        f"Items ({len(situations)} items):\n{_numbered(situations)}\n\n"
        f"Return exactly {len(situations)} situation_judgments, one per "
        "item, same order."
    )
    result = await llm.ainvoke(prompt)

    if len(result.situation_judgments) != len(situations):
        raise ValueError(
            f"classify_relevance count mismatch for topic={topic!r}: "
            f"{len(result.situation_judgments)}/{len(situations)}"
        )

    return [
        {"situation": text, "verdict": j.verdict, "reason": j.reason}
        for text, j in zip(situations, result.situation_judgments)
    ]
