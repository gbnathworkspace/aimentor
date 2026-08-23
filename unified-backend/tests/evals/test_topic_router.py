"""Eval: topic_router.route_topic's MATCH / AMBIGUOUS / NEW decision quality
against hand-labeled cases.

This is a QUALITY eval, not a unit test (unit-level plumbing/fallback
behavior is already covered by tests/unit/test_topic_router.py with a
mocked LLM). This eval makes real calls to the Anthropic API (Haiku) and
checks route_topic's decisions against
tests/evals/topic_router_cases.py's hand-labeled set. It costs money and
needs a real ANTHROPIC_API_KEY, so it's skipped by default and excluded
from the normal `pytest` run.

Run it explicitly:
    RUN_EVALS=1 pytest tests/evals/test_topic_router.py -v -s

(PowerShell: `$env:RUN_EVALS = "1"; pytest tests/evals/test_topic_router.py -v -s`)

Every run writes a full report — every case, not just misses — to
tests/evals/reports/, so results can be cross-checked without rerunning.

Run whenever topic_router's system prompt or tool schema changes — this is
a regression suite for routing quality, not a one-time check.
"""

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.topic_router import route_topic
from tests.evals.topic_router_cases import EVAL_CASES

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_EVALS") != "1",
    reason="Hits the live Anthropic API — set RUN_EVALS=1 to run (see module docstring).",
)

_DEFAULT_BAR = 0.90
_CATEGORY_BAR = {"ambiguous": 0.75}

_REPORTS_DIR = Path(__file__).parent / "reports"


def _score(case: dict, result) -> tuple[bool, str]:
    """Returns (correct, got_summary) for one case — see module/cases-file
    docstrings for the scoring rule per expected decision type."""
    expected = case["expected"]

    if expected["decision"] == "NEW":
        correct = result.topic_id is None and not result.related_ids
        got = f"topic_id={result.topic_id!r} related_ids={result.related_ids!r}"
        return correct, got

    if expected["decision"] == "MATCH":
        target = expected["topic_id"]
        correct = result.topic_id == target or target in result.related_ids
        got = f"topic_id={result.topic_id!r} related_ids={result.related_ids!r}"
        return correct, got

    # AMBIGUOUS: any acceptable id surfaced, as a MATCH or inside related_ids.
    acceptable = set(expected["acceptable"])
    surfaced = ({result.topic_id} if result.topic_id else set()) | set(result.related_ids)
    correct = bool(surfaced & acceptable)
    got = f"topic_id={result.topic_id!r} related_ids={result.related_ids!r}"
    return correct, got


def _write_report(case_rows: list[dict], category_stats: list[tuple[str, int, int, float, bool]]) -> Path:
    _REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = _REPORTS_DIR / f"topic_router_{stamp}.md"

    overall_pass = all(ok for _, _, _, _, ok in category_stats)
    lines = [
        f"# topic_router eval — {stamp}",
        "",
        f"**Result: {'PASS' if overall_pass else 'FAIL'}** — "
        f"{sum(r['correct'] for r in case_rows)}/{len(case_rows)} cases correct.",
        "",
        "## Per-category accuracy",
        "",
        "| Category | Accuracy | Correct | Bar | Status |",
        "|---|---|---|---|---|",
    ]
    for category, correct_n, total_n, bar, ok in category_stats:
        lines.append(
            f"| {category} | {correct_n / total_n:.0%} | {correct_n}/{total_n} "
            f"| {bar:.0%} | {'OK' if ok else '**BELOW BAR**'} |"
        )

    lines += ["", "## Every case",
              "", "| # | Category | Query | Expected | Got | Correct |",
              "|---|---|---|---|---|---|"]
    for i, r in enumerate(case_rows, 1):
        mark = "✅" if r["correct"] else "❌"
        query_preview = r["query"][:60] + ("…" if len(r["query"]) > 60 else "")
        lines.append(f"| {i} | {r['category']} | {query_preview} | {r['expected']} | {r['got']} | {mark} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_topic_router_accuracy():
    results: dict[str, list[bool]] = defaultdict(list)
    case_rows: list[dict] = []

    for case in EVAL_CASES:
        result = await route_topic(case["query"], case["topics"])
        correct, got = _score(case, result)
        results[case["category"]].append(correct)
        case_rows.append({
            "category": case["category"],
            "query": case["query"],
            "expected": case["expected"],
            "got": got,
            "correct": correct,
        })

    print("\ntopic_router eval — per-category accuracy:")
    below_bar = []
    category_stats = []
    for category, outcomes in sorted(results.items()):
        accuracy = sum(outcomes) / len(outcomes)
        bar = _CATEGORY_BAR.get(category, _DEFAULT_BAR)
        ok = accuracy >= bar
        category_stats.append((category, sum(outcomes), len(outcomes), bar, ok))
        print(f"  {category:26s} {accuracy:5.0%}  ({sum(outcomes)}/{len(outcomes)})  bar={bar:.0%}  "
              f"{'OK' if ok else 'BELOW BAR'}")
        if not ok:
            below_bar.append(category)

    misses = [r for r in case_rows if not r["correct"]]
    if misses:
        print("\nMisclassifications:")
        for r in misses:
            print(f"  - [{r['category']}] query={r['query'][:60]!r} "
                  f"expected={r['expected']} got={r['got']}")

    report_path = _write_report(case_rows, category_stats)
    print(f"\nFull report written to: {report_path}")

    assert not below_bar, f"Categories below accuracy bar: {below_bar} — see {report_path}"
