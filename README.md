<img src="mentorman-web/public/logo-full.svg" alt="MentorMan" height="60" />


A goal-aware AI mentor — built around one core insight: **the LLM is a stateless reasoning engine; the databases are its memory.**

Live at [mentorman.co.in](https://mentorman.co.in)

---

## Why This Exists

Generic AI chat gives the same answer whether it's your first session or your fiftieth. MentorMan doesn't. On every call, it assembles a fresh context from three memory layers — your goal, your current skill gaps, and relevant past sessions — so the mentor always knows exactly where you are and what matters next.

---

## Architecture: 3-Layer Memory

The most interesting design decision in this system is how memory is structured and injected.

```
Layer 1 — Core Profile        always injected, filtered per topic
  Free-text "Facts About You" (situations) + style notes
  (pacing, communication, motivation, misconceptions, context)
  A Haiku classification call scopes which facts are relevant
  to the current topic, cached until the profile changes

Layer 2 — Skill Graph         topic-filtered query
  per-topic: current_level, signals, prerequisites, assessed
  current_level starts at a seeded guess, then updates from real
  evidence (diagnostic verdicts, session-end extraction). No
  required_level/gap — those were a flat, non-goal-derived constant
  and were removed rather than kept as fake precision

Layer 3 — Episodic Memory     topic-scoped, recency-based
  Topic's own rolling summary + that topic's past session summaries
  Session summaries ARE embedded via Voyage AI at session end and
  written to Atlas Vector Search — but nothing reads them back yet.
  Retrieval today is "most recent," not semantic similarity.

Conversation history           rolling window
```

**Why not vector search for retrieval yet?** The write path exists (Voyage AI embeddings, Atlas Vector Search upsert on every session end) but the read path doesn't query them — recency-based fetch avoids a missing Atlas index and a writer/reader collection mismatch that haven't been resolved. This is a known gap, not a design choice: semantic retrieval over past sessions is the natural next step once that's fixed.

**Why not two databases?** MongoDB Atlas Vector Search would handle all three layers in one cluster (one connection, one IAM role, one failure surface) once retrieval is wired up. Pinecone would give marginally better retrieval at scale — not a measurable problem for a single user's session history.

---

## Session Intelligence

The mentor detects session mode from the user's first message. It's never user-selected.

| Mode | What it does |
|---|---|
| **Planning** | Builds a study plan prioritised by prerequisite order |
| **Topic** | Teaches the concept, probes understanding depth |
| **Doubt** | Resolves the specific gap, checks root cause |
| **Evaluation** | Recall → Application → Depth question sequence |

At session end, one Sonnet call over the full transcript produces two outputs:
- `narrative_summary` → embedded via Voyage AI → written to Layer 3
- `skill_update` → upserted into the skill graph → updates Layer 2

**Signal conflict rule:** Active mentor evaluation always beats passive LeetCode history. No weighting formula — active signal is higher quality, full stop.

---

## Agent Loop

The mentor isn't a single LLM call per turn — it's a bounded ReAct-style tool loop (`topic_chat_service.py`): reason → optionally call a tool → observe the result → reason again, up to 2 rounds (worst case: one tool-decision call + one forced-final-answer call, so latency stays bounded instead of looping unboundedly).

Tools bound with `tool_choice="auto"` (the model decides whether to act):

| Tool | Purpose |
|---|---|
| `web_search` | Native Claude web search, capped at 3 uses per turn |
| `get_skill_detail` | Look up current level for a topic other than the one being discussed |
| `record_diagnostic_verdict` | Diagnostic-mode only — records an assessed skill level once there's enough signal, in the same call as the reply text rather than a separate round trip |

On the final round, `get_skill_detail` is stripped from the tool set so the model is forced to answer instead of requesting another lookup — this is the hard stop on the loop. `record_diagnostic_verdict` is never treated as a loop tool: calling it always ends the turn.

---

## Skill Graph Design

Proficiency is tracked per topic from real evidence — diagnostic verdicts, session-end extraction — not self-reported. There's no goal-specific target to compare against yet (a Goal Knowledge Base was planned but never built), so this tracks absolute level, not a goal-relative gap.

```json
{
  "topic": "graphs",
  "current_level": "easy",
  "assessed": true,
  "prerequisites": ["arrays"],
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
    "mentor_eval_score": "3/5",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS", "cycle detection"]
  }
}
```

The schema is LLM-generated per user at onboarding. Different goals produce different topic sets — no developer involvement per user.

---

## Tech Stack

| | |
|---|---|
| **Frontend** | React + Vite (SPA) |
| **Backend** | FastAPI (Python) |
| **Auth** | Self-hosted (JWT + refresh tokens, OAuth, OTP) |
| **LLM — main** | Claude Sonnet 4.6 — reasoning, responses, evals, summaries |
| **LLM — lightweight** | Claude Haiku 4.5 — intent checks, drift detection, titles |
| **Embeddings** | Voyage AI voyage-4-lite — 200M tokens/month free |
| **Database** | MongoDB Atlas M0 — structured + vector in one cluster |
| **Hosting** | EC2 t2.micro + nginx — flat cost, no bill-shock risk |
| **Secrets** | AWS SSM Parameter Store — no credentials on the instance |

Everything runs on free tiers except Anthropic API usage.

---

## Running Locally

```bash
# Backend — FastAPI on :8000
cd unified-backend
cp .env.example .env        # fill in ANTHROPIC_API_KEY, MONGODB_URI, VOYAGE_API_KEY
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# Frontend — Vite SPA on :5173
cd mentorman-web
npm run dev
```

---
