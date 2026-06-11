# MentorMan

A goal-aware AI mentor for software engineering interview prep — built around one core insight: **the LLM is a stateless reasoning engine; the databases are its memory.**

Live at [mentorman.co.in](https://mentorman.co.in)

---

## Why This Exists

Generic AI chat gives the same answer whether it's your first session or your fiftieth. MentorMan doesn't. On every call, it assembles a fresh context from three memory layers — your goal, your current skill gaps, and relevant past sessions — so the mentor always knows exactly where you are and what matters next.

---

## Architecture: 3-Layer Memory

The most interesting design decision in this system is how memory is structured and injected.

```
Layer 1 — Core Profile        ~200 tokens · always injected
  goal, deadline, availability
  Small and stable — no retrieval cost

Layer 2 — Skill Graph         ~400 tokens · topic-filtered query
  per-topic: current_level, required_level, gap, signals
  Gap = required_level − current_level (goal-relative, not absolute)

Layer 3 — Episodic Memory     ~300 tokens · conditionally retrieved
  session summaries + resolved doubts, embedded via Voyage AI
  A Haiku intent pre-check gates retrieval — most calls skip it entirely

Goal anchor                    ~50 tokens · repeated at bottom
  Fights "lost in the middle" attention decay on long contexts

Conversation history           ~500 tokens · rolling 6-turn window
─────────────────────────────────────────────────────────────────
Total context budget per call: ~1,550 tokens
```

**Why not a flat vector store?** Structured facts (gap %, deadlines) should be queried directly, not retrieved by cosine similarity. Vector search is reserved for episodic memory — the one layer where semantic retrieval actually makes sense.

**Why not two databases?** MongoDB Atlas Vector Search handles all three layers in one cluster (one connection, one IAM role, one failure surface). Pinecone would give marginally better retrieval at scale — not a measurable problem for a single user's session history.

---

## Session Intelligence

The mentor detects session mode from the user's first message. It's never user-selected.

| Mode | What it does |
|---|---|
| **Planning** | Builds a study plan prioritised by skill gap |
| **Topic** | Teaches the concept, probes understanding depth |
| **Doubt** | Resolves the specific gap, checks root cause |
| **Evaluation** | Recall → Application → Depth question sequence |

At session end, one Sonnet call over the full transcript produces two outputs:
- `narrative_summary` → embedded via Voyage AI → written to Layer 3
- `skill_update` → upserted into the skill graph → updates Layer 2

**Signal conflict rule:** Active mentor evaluation always beats passive LeetCode history. No weighting formula — active signal is higher quality, full stop.

---

## Skill Graph Design

Proficiency is measured relative to the user's goal, not in absolute terms. The `required_level` per topic comes from a curated Goal Knowledge Base (sourced from Glassdoor interviews and Naukri JDs) — never guessed by the LLM.

```json
{
  "topic": "graphs",
  "current_level": "easy",
  "required_level": "medium",
  "gap": "40%",
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
| **Auth** | Clerk (JWT verified networklessly via JWKS) |
| **LLM — main** | Claude Sonnet 4.6 — reasoning, responses, evals, summaries |
| **LLM — lightweight** | Claude Haiku 4.5 — intent checks, drift detection, titles |
| **Embeddings** | Voyage AI voyage-4-lite — 200M tokens/month free |
| **Database** | MongoDB Atlas M0 — structured + vector in one cluster |
| **Hosting** | EC2 t2.micro + nginx — flat cost, no bill-shock risk |
| **Secrets** | AWS SSM Parameter Store — no credentials on the instance |

Everything runs on free tiers except Anthropic API usage.

---

## Key Engineering Decisions

**Zod as the layer boundary contract.** The LLM writes structured JSON (skill updates, onboarding outputs). Zod validates every LLM write before it hits MongoDB — silent schema drift is caught at runtime, not discovered in production.

**Prompt versioning in Git, not a database.** Prompts need diffs, review, and rollback. Git is the right tool.

**EC2 over Vercel.** Already paying for the instance. Vercel per-request billing has no hard cap — traffic spikes change the bill. EC2 is flat rate.

**IAM role auth for MongoDB.** No credentials on the EC2 instance. The attached IAM role proves identity to Atlas automatically.

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

## Build Status

| Feature | Status |
|---|---|
| Chat UI — session history, recovery, file upload | Done |
| Onboarding flow | Done |
| Backend API — sessions, skills, profile, mentor | Done |
| Context assembler (Layer 1 + 2 injection) | In progress |
| Streaming responses (SSE) | Planned |
| Episodic memory retrieval (Atlas Vector Search) | Planned |
| Full evaluation loop with skill graph updates | Planned |

---

*Personal project · Solo build · Target: 20 LPA SWE role by Aug 2026*
