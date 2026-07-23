"""DeriveSubtopicWeights — allocates a 100-point weight budget across a
topic's subtopics from real evidence (job postings/interview questions for
interview_prep, the user's own commits/tickets/PR comments for
job_performance), instead of guessing or weighting everything equally.

See .kiro/specs/skill-graph-v2/design.md for the taxonomy this feeds into.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

import anthropic

from app.config.database import subtopic_lists_col
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

Goal = Literal["interview_prep", "job_performance"]

NUDGE_CAP = 15.0  # max points a user can shift a subtopic away from baseline
FLAG_THRESHOLD = NUDGE_CAP * 0.7  # near-max nudge = notable disagreement signal
MIN_EVIDENCE_THRESHOLD = 5  # absolute floor regardless of subtopic count
MIN_EVIDENCE_PER_SUBTOPIC = 1.5  # scales the floor up as more subtopics compete for mentions
SMOOTHING = 1  # Laplace/add-one smoothing — a real subtopic the counter missed
# should read as "rare", not "confirmed absent" (weight 0 forever)

# ponytail: flat cap matching topic_chat_service's search budget, no per-user
# tuning until usage data justifies it.
WEB_SEARCH_MAX_USES = 3
HAIKU_MODEL = "claude-haiku-4-5-20251001"
EVIDENCE_CHAR_LIMIT = 8000  # cap prompt size for the mention-counting call


@dataclass
class WeightFlag:
    subtopic: str
    baseline: float
    final: float
    delta: float


@dataclass
class WeightResult:
    weights: dict[str, float] | None
    flags: list[WeightFlag] = field(default_factory=list)
    # True when evidence was too sparse to count — caller must collect a
    # pairwise ranking from the user and re-call with pairwise_comparisons.
    needs_pairwise: bool = False


async def get_subtopics(topic: str) -> list[str]:
    """Decompose `topic` into subtopics, cached per topic (case-insensitive).

    Not the full skill-graph-v2 taxonomy (no target/difficulty/prereqs) —
    just the flat subtopic list this feature needs. Add the fuller shape
    if/when that spec ships and something else needs prereqs too.
    """
    cache_key = topic.strip().lower()
    cached = await subtopic_lists_col().find_one({"topic": cache_key})
    if cached:
        return cached["subtopics"]

    subtopics = await _decompose_via_llm(topic)
    await subtopic_lists_col().update_one(
        {"topic": cache_key},
        {"$set": {"topic": cache_key, "subtopics": subtopics}},
        upsert=True,
    )
    return subtopics


async def _decompose_via_llm(topic: str) -> list[str]:
    """Call Haiku to generate 5-8 concept-level subtopics for `topic`."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                f"List 5-8 concept-level subtopics someone must learn to master '{topic}'. "
                "Each should be a short phrase (3-6 words), specific enough to count mentions "
                "of it in text (e.g. 'cold starts & provisioned concurrency', not 'performance'). "
                "Return ONLY a JSON array of strings, no explanation. Example: "
                '["Subtopic 1", "Subtopic 2", "Subtopic 3"]'
            ),
        }],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()

    try:
        subtopics = json.loads(text)
        if isinstance(subtopics, list) and all(isinstance(s, str) for s in subtopics):
            return subtopics[:8]
    except json.JSONDecodeError:
        pass

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        subtopics = json.loads(text[start : end + 1])
        if isinstance(subtopics, list) and all(isinstance(s, str) for s in subtopics):
            return subtopics[:8]

    raise ValueError(f"Could not parse subtopics from LLM response for topic={topic!r}")


async def _gather_evidence(
    goal: Goal, topic: str, target_context: str | None, work_evidence: str | None
) -> str:
    if goal == "interview_prep":
        settings = get_settings()
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        context = target_context or topic
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2000,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": WEB_SEARCH_MAX_USES,
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Search for job postings and common interview questions "
                    f"for '{topic}', relevant to: {context}. "
                    f"Return the raw text you find — do not summarize."
                ),
            }],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    if goal == "job_performance":
        if not work_evidence:
            raise ValueError(
                "goal='job_performance' requires work_evidence "
                "(recent commits, tickets, PR review comments)"
            )
        return work_evidence

    raise ValueError(f"goal must be 'interview_prep' or 'job_performance', got {goal!r}")


async def _count_mentions_llm(evidence: str, subtopics: list[str]) -> dict[str, int]:
    """Count how many times each subtopic is discussed in `evidence` — a
    semantic judgment call, not exact-string search. Evidence text (job
    postings, pasted commits) never uses a subtopic's literal LLM-generated
    name verbatim, so substring matching would always read as zero.
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    subtopic_list = "\n".join(f"- {s}" for s in subtopics)

    response = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": (
                f'Evidence:\n"""\n{evidence[:EVIDENCE_CHAR_LIMIT]}\n"""\n\n'
                f"Subtopics:\n{subtopic_list}\n\n"
                "For each subtopic, count how many distinct times the evidence discusses, "
                "mentions, or clearly implies it — even under different wording (e.g. "
                "'set up build environments' counts toward a subtopic about build "
                "configuration). A subtopic never touched on gets 0. "
                "Return ONLY a JSON object mapping each subtopic name (exactly as given) "
                'to an integer count, no explanation. Example: {"Subtopic 1": 3, "Subtopic 2": 0}'
            ),
        }],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    counts = _parse_json_object(text)
    return {s: int(counts.get(s, 0)) for s in subtopics}


def _parse_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])

    raise ValueError(f"Could not parse a JSON object from LLM response: {text[:200]!r}")


def pairwise_wins_to_counts(
    comparisons: list[tuple[str, str]], subtopics: list[str]
) -> dict[str, int]:
    """AHP-lite fallback: turn (winner, loser) pairwise picks into raw counts."""
    wins = Counter({s: 0 for s in subtopics})
    for winner, _loser in comparisons:
        wins[winner] += 1
    return dict(wins)


def _normalize(counts: dict[str, float]) -> dict[str, float]:
    total = sum(counts.values())
    if total == 0:
        return {s: 100.0 / len(counts) for s in counts}
    return {s: (v / total) * 100 for s, v in counts.items()}


def apply_nudges(
    baseline: dict[str, float], user_nudges: dict[str, float]
) -> tuple[dict[str, float], list[WeightFlag]]:
    """Clamp each user nudge to +-NUDGE_CAP, re-normalize to 100, and flag any
    subtopic whose final weight moved more than 70% of the cap from baseline.
    """
    nudged = {
        s: baseline[s] + max(-NUDGE_CAP, min(NUDGE_CAP, user_nudges.get(s, 0.0)))
        for s in baseline
    }
    final = _normalize(nudged)
    flags = [
        WeightFlag(s, baseline[s], final[s], final[s] - baseline[s])
        for s in baseline
        if abs(final[s] - baseline[s]) > FLAG_THRESHOLD
    ]
    return final, flags


async def derive_subtopic_weights(
    topic: str,
    goal: Goal,
    subtopics: list[str],
    target_context: str | None = None,
    work_evidence: str | None = None,
    pairwise_comparisons: list[tuple[str, str]] | None = None,
    user_nudges: dict[str, float] | None = None,
) -> WeightResult:
    """Weight each subtopic by how prominently it shows up in evidence for
    `goal`, then apply any bounded user nudges on top.

    Pass `pairwise_comparisons` directly to skip evidence-gathering and use
    the AHP-lite fallback (e.g. on a retry after `needs_pairwise=True`).
    """
    if pairwise_comparisons is not None:
        counts = pairwise_wins_to_counts(pairwise_comparisons, subtopics)
        baseline = _normalize(counts)
    else:
        evidence = await _gather_evidence(goal, topic, target_context, work_evidence)
        counts = await _count_mentions_llm(evidence, subtopics)
        threshold = max(MIN_EVIDENCE_THRESHOLD, MIN_EVIDENCE_PER_SUBTOPIC * len(subtopics))
        if sum(counts.values()) < threshold:
            logger.info(
                "Sparse evidence for topic=%s goal=%s counts=%s (threshold=%.1f) — need pairwise ranking",
                topic, goal, counts, threshold,
            )
            return WeightResult(weights=None, needs_pairwise=True)
        # Smoothed only here: a count-of-0 from a thin sample means "rare",
        # not "confirmed zero" — pairwise ranks above are a real signal, not
        # sampling noise, so they're normalized unsmoothed.
        baseline = _normalize({s: c + SMOOTHING for s, c in counts.items()})

    final, flags = apply_nudges(baseline, user_nudges or {})
    return WeightResult(weights=final, flags=flags)
