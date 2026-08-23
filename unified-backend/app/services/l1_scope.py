"""classify_relevance — judges L1 situations/contexts/focus_areas against a topic.

Used to compute `l1_scope`, cached on the topic document (see
TopicService._ensure_l1_scope), so mentor prompts inject only the
situations/contexts relevant to the topic being discussed instead of
flattening the user's full profile lists into every turn — and so
SubtopicWeightsModal's goal-picker only offers focus areas that actually
overlap the topic being weighted (see .kiro/specs/topic-scoping).
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
    """Position-aligned to the input lists, not keyed by re-echoed text."""

    situation_judgments: list[_Judgment]
    context_judgments: list[_Judgment]
    focus_area_judgments: list[_Judgment]


def extract_situations_and_contexts(profile: dict) -> tuple[list[str], list[str]]:
    """Pull situations/contexts out of a profile doc, folding `label` into
    situations. Shared by classify_relevance's input and
    prompt_store._format_learning_context's fallback so both use one
    definition instead of two that can drift apart.
    """
    detail = profile.get("learning_context_detail") or {}
    contexts = list(detail.get("contexts") or [])
    if not contexts and profile.get("learning_context"):
        contexts = [str(profile["learning_context"])]

    situations = list(detail.get("situations") or [])
    label = detail.get("label")
    if label and label not in situations:
        situations.insert(0, label)

    return situations, contexts


def extract_focus_areas(profile: dict) -> list[str]:
    """Pull focus_areas out of a profile doc — a separate top-level field
    from situations/contexts, but judged for topic relevance the same way
    (it's profile-wide, not topic-scoped, per SubtopicWeightsModal's own
    buildGoalCards comment)."""
    return list(profile.get("focus_areas") or [])


def compute_profile_stamp(situations: list[str], contexts: list[str], focus_areas: list[str]) -> str:
    """Stable hash of all three lists — cheap equality check for staleness,
    no TTL, no invalidation logic."""
    payload = json.dumps(
        {"situations": situations, "contexts": contexts, "focus_areas": focus_areas},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i + 1}. {text}" for i, text in enumerate(items)) or "(none)"


async def classify_relevance(
    topic: str, situations: list[str], contexts: list[str], focus_areas: list[str] | None = None,
) -> list[dict]:
    """One shared Haiku call judging every situation/context/focus_area
    against `topic`.

    Returns [{"situation": str, "verdict": "relevant"|"irrelevant"|"uncertain",
    "reason": str}, ...], one entry per input item, in `situations +
    contexts + focus_areas` order. Returns [] immediately, no LLM call, if
    all three lists are empty.

    Raises ValueError if the model returns a different number of judgments
    than items given, rather than silently pairing mismatched positions.
    """
    focus_areas = focus_areas or []
    if not situations and not contexts and not focus_areas:
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
        f"Situations ({len(situations)} items):\n{_numbered(situations)}\n\n"
        f"Contexts ({len(contexts)} items):\n{_numbered(contexts)}\n\n"
        f"Focus areas ({len(focus_areas)} items):\n{_numbered(focus_areas)}\n\n"
        f"Return exactly {len(situations)} situation_judgments (one per "
        f"situation, same order), exactly {len(contexts)} context_judgments "
        f"(one per context, same order), and exactly {len(focus_areas)} "
        "focus_area_judgments (one per focus area, same order)."
    )
    result = await llm.ainvoke(prompt)

    if (len(result.situation_judgments) != len(situations)
            or len(result.context_judgments) != len(contexts)
            or len(result.focus_area_judgments) != len(focus_areas)):
        raise ValueError(
            f"classify_relevance count mismatch for topic={topic!r}: "
            f"situations {len(result.situation_judgments)}/{len(situations)}, "
            f"contexts {len(result.context_judgments)}/{len(contexts)}, "
            f"focus_areas {len(result.focus_area_judgments)}/{len(focus_areas)}"
        )

    return [
        {"situation": text, "verdict": j.verdict, "reason": j.reason}
        for text, j in zip(situations, result.situation_judgments)
    ] + [
        {"situation": text, "verdict": j.verdict, "reason": j.reason}
        for text, j in zip(contexts, result.context_judgments)
    ] + [
        {"situation": text, "verdict": j.verdict, "reason": j.reason}
        for text, j in zip(focus_areas, result.focus_area_judgments)
    ]
