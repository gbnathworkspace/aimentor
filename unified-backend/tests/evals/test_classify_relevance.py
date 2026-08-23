"""Eval: classify_relevance judgment quality against hand-labeled cases.

This is a QUALITY eval, not a unit test — it makes real calls to the
Anthropic API (Haiku) and checks the model's judgments against
tests/evals/classify_relevance_cases.py's hand-labeled set. It costs money
and needs a real ANTHROPIC_API_KEY, so it's skipped by default and excluded
from the normal `pytest` run.

Run it explicitly:
    RUN_EVALS=1 pytest tests/evals/test_classify_relevance.py -v -s

(PowerShell: `$env:RUN_EVALS = "1"; pytest tests/evals/test_classify_relevance.py -v -s`)

Every run writes a full report — every case, not just misses — to
tests/evals/reports/, so results can be cross-checked without rerunning.

Run whenever classify_relevance's prompt changes — this is a regression
suite for judgment quality, not a one-time check.
"""

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.l1_scope import classify_relevance
from tests.evals.classify_relevance_cases import EVAL_CASES

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_EVALS") != "1",
    reason="Hits the live Anthropic API — set RUN_EVALS=1 to run (see module docstring).",
)

# Per-category accuracy bar. Ambiguous cases get a lower bar on purpose —
# the source doc: "don't expect 100% on genuinely hard judgment calls."
_DEFAULT_BAR = 0.90
_CATEGORY_BAR = {"ambiguous_hard": 0.75}

_REPORTS_DIR = Path(__file__).parent / "reports"


def _write_report(case_rows: list[dict], category_stats: list[tuple[str, int, int, float, bool]]) -> Path:
    _REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    path = _REPORTS_DIR / f"classify_relevance_{stamp}.md"

    overall_pass = all(ok for _, _, _, _, ok in category_stats)
    lines = [
        f"# classify_relevance eval — {stamp}",
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
              "", "| # | Category | Topic | Text | Expected | Verdict | Included | Correct | Reason |",
              "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(case_rows, 1):
        mark = "✅" if r["correct"] else "❌"
        lines.append(
            f"| {i} | {r['category']} | {r['topic']} | {r['text']} | {r['expected']} | "
            f"{r['verdict']} | {r['got']} | {mark} | {r['reason']} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_classify_relevance_accuracy():
    results: dict[str, list[bool]] = defaultdict(list)
    case_rows: list[dict] = []

    for case in EVAL_CASES:
        judgments = await classify_relevance(case["topic"], [case["text"]])
        verdict = judgments[0]["verdict"]
        # "uncertain" is included, same as production's interim policy
        # (see prompt_store._format_learning_context) — scored against
        # actual system behavior, not treated as automatically wrong.
        got = verdict != "irrelevant"
        correct = got == case["expected_relevant"]
        results[case["category"]].append(correct)
        case_rows.append({
            "category": case["category"],
            "topic": case["topic"],
            "text": case["text"],
            "expected": case["expected_relevant"],
            "verdict": verdict,
            "got": got,
            "correct": correct,
            "reason": judgments[0]["reason"],
        })

    print("\nclassify_relevance eval — per-category accuracy:")
    below_bar = []
    category_stats = []
    for category, outcomes in sorted(results.items()):
        accuracy = sum(outcomes) / len(outcomes)
        bar = _CATEGORY_BAR.get(category, _DEFAULT_BAR)
        ok = accuracy >= bar
        category_stats.append((category, sum(outcomes), len(outcomes), bar, ok))
        print(f"  {category:28s} {accuracy:5.0%}  ({sum(outcomes)}/{len(outcomes)})  bar={bar:.0%}  "
              f"{'OK' if ok else 'BELOW BAR'}")
        if not ok:
            below_bar.append(category)

    misses = [r for r in case_rows if not r["correct"]]
    if misses:
        print("\nMisclassifications:")
        for r in misses:
            print(f"  - [{r['category']}] topic={r['topic']!r} text={r['text']!r} "
                  f"expected={r['expected']} got={r['got']} reason={r['reason']!r}")

    report_path = _write_report(case_rows, category_stats)
    print(f"\nFull report written to: {report_path}")

    assert not below_bar, f"Categories below accuracy bar: {below_bar} — see {report_path}"
