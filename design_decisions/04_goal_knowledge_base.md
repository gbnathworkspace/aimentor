# Goal Knowledge Base

## Decision
Goals are user-defined — not a pre-set list.
KB is seeded with common goals for reliability.
LLM derives requirements dynamically for goals not in the KB.

## Why
Users should be free to state any goal conversationally.
Pre-defined lists are restrictive and miss edge cases.
But pure LLM guessing is inconsistent — so common goals get
curated KB entries as a reliable fallback.

## Two-tier approach

Tier 1 — Seeded common goals (curated, high reliability)
  20 LPA, 30 LPA, FAANG, service-based company, AWS certification
  Sourced from Glassdoor, Naukri, prep sites.

Tier 2 — LLM-derived on the fly (for any other goal)
  User states goal → LLM reasons what it requires per topic
  → KB entry created and stored for future use

## What it stores
```json
{
  "goal": "20 LPA",
  "source": "curated",
  "requirements": {
    "arrays":         "medium",
    "graphs":         "medium",
    "DP":             "medium",
    "system_design":  "basic",
    "AWS":            "basic"
  }
}
```

source field: "curated" or "llm_derived"

## How it's used
At onboarding: user states goal freely in conversation →
KB queried for match → if found, use curated entry →
if not, LLM derives requirements → stored as llm_derived entry →
required_level set for each skill graph node.

When goal evolves: KB queried again for new goal →
required_level updated across all nodes → gaps recalculated.

## Refresh cadence
Refresh cadence: manual trigger for v1.
Admin triggers a re-fetch when interview patterns feel stale.
Move to monthly cron in v2 when user base grows.
