"""Eval: mode_router.route_user_turn's rule-selection quality against
hand-labeled cases.

This is a QUALITY eval, not a unit test (unit-level plumbing/fallback
behavior is already covered by tests/unit/test_mode_router.py with a
mocked LLM). This eval makes real calls to the Anthropic API (Haiku) and
checks route_user_turn's chosen mode against
tests/evals/mode_router_cases.py's hand-labeled set. It costs money and
needs a real ANTHROPIC_API_KEY, so it's skipped by default and excluded
from the normal `pytest` run.

Run it explicitly:
    RUN_EVALS=1 pytest tests/evals/test_mode_router.py -v -s

(PowerShell: `$env:RUN_EVALS = "1"; pytest tests/evals/test_mode_router.py -v -s`)

Every run writes a full report — every case, not just misses — to
tests/evals/reports/, so results can be cross-checked without rerunning.

Run whenever mode_router's rule prompt changes — this is a regression
suite for routing quality, not a one-time check.
"""

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.mode_router import route_user_turn
from tests.evals.mode_router_cases import EVAL_CASES

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_EVALS") != "1",
    reason="Hits the live Anthropic API — set RUN_EVALS=1 to run (see module docstring).",
)

_DEFAULT_BAR = 0.90
_CATEGORY_BAR = {"urgency_casualness_confound": 0.75}

_REPORTS_DIR = Path(__file__).parent / "reports"


def _write_report(case_rows: list[dict], category_stats: list[tuple[str, int, int, float, bool]]) -> Path:
    _REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = _REPORTS_DIR / f"mode_router_{stamp}.md"

    overall_pass = all(ok for _, _, _, _, ok in category_stats)
    lines = [
        f"# mode_router eval — {stamp}",
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
              "", "| # | Category | Query | Expected | Got | Rule | Correct | Reasoning |",
              "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(case_rows, 1):
        mark = "✅" if r["correct"] else "❌"
        query_preview = r["query"][:60] + ("…" if len(r["query"]) > 60 else "")
        lines.append(
            f"| {i} | {r['category']} | {query_preview} | {r['expected']} | "
            f"{r['got']} | {r['rule']} | {mark} | {r['reasoning']} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_mode_router_accuracy():
    results: dict[str, list[bool]] = defaultdict(list)
    case_rows: list[dict] = []

    for case in EVAL_CASES:
        decision = await route_user_turn(
            query=case["query"],
            skill=case["skill"],
            recent_messages=case["recent_messages"],
            profile=case.get("profile"),
        )
        got = decision.selected_mode.value
        correct = got == case["expected_mode"]
        results[case["category"]].append(correct)
        case_rows.append({
            "category": case["category"],
            "query": case["query"],
            "expected": case["expected_mode"],
            "got": got,
            "rule": decision.matched_rule.value,
            "correct": correct,
            "reasoning": decision.reasoning,
        })

    print("\nmode_router eval — per-category accuracy:")
    below_bar = []
    category_stats = []
    for category, outcomes in sorted(results.items()):
        accuracy = sum(outcomes) / len(outcomes)
        bar = _CATEGORY_BAR.get(category, _DEFAULT_BAR)
        ok = accuracy >= bar
        category_stats.append((category, sum(outcomes), len(outcomes), bar, ok))
        print(f"  {category:32s} {accuracy:5.0%}  ({sum(outcomes)}/{len(outcomes)})  bar={bar:.0%}  "
              f"{'OK' if ok else 'BELOW BAR'}")
        if not ok:
            below_bar.append(category)

    misses = [r for r in case_rows if not r["correct"]]
    if misses:
        print("\nMisclassifications:")
        for r in misses:
            print(f"  - [{r['category']}] query={r['query'][:60]!r} "
                  f"expected={r['expected']} got={r['got']} rule={r['rule']} reasoning={r['reasoning']!r}")

    report_path = _write_report(case_rows, category_stats)
    print(f"\nFull report written to: {report_path}")

    assert not below_bar, f"Categories below accuracy bar: {below_bar} — see {report_path}"
