# MentorMan — System Architecture

> **Last updated:** May 2026  
> **Status:** Reference document — update when service boundaries or data layer changes

---

## Overview

MentorMan uses a strict 3-layer architecture. The LLM is the reasoning engine — it has no native memory of its own. The two databases *are* its memory, assembled fresh on every call.

```
UI Layer  →  Service Layer  →  Data Layer  →  LLM
```

Changes to the UI should never require touching the data layer. Changes to the LLM prompts should never require touching the UI. Each layer has one job.

---

## Layer 1 — UI (React / Next.js 14, App Router)

| Screen | Route | Notes |
|---|---|---|
| Onboarding (goal) | `/onboarding` | Screen 1 — chat-style, no forms |
| Onboarding (availability) | `/onboarding/availability` | Screen 7 — final step, setup complete card |
| Main Chat (live) | `/session/[id]` | Screen 2 — mode tag in input bar, alert banners |
| Past Session (read-only) | `/session/[id]` | Screen 3 — same route, read-only state |
| Skill Graph Dashboard | `/skill-graph` | Screen 5 — gap bars, biggest gaps CTA |
| Evaluation Mode | `/session/[id]/eval` | Screen 6 — Q→verdict flow, submit answer |
| Session End Summary | `/session/[id]/summary` | Screen 8 — narrative recap, skill delta |
| In-App Alert Banner | (component) | Screen 9 — injected above chat |
| Settings | `/settings` | Screen 10 — goal, deadline, availability, data sources |

**Rules:**
- UI components receive typed props only — no raw DB shapes ever reach a component
- Clerk JWT is validated at every API route before any service call
- Design tokens (colors, spacing, typography) live in `globals.css` — never hardcoded in components

---

## Layer 2 — Service Layer (Business Logic)

Each service owns one domain. No service imports from another service's internals.

### `SessionService`
- Detects session mode (Planning / Topic / Doubt / Evaluation) from the user's first message
- Selects the versioned prompt for that mode from the Prompt Store
- Applies nudge logic when the user drifts off-topic
- Manages session lifecycle (start, pause, end, summary generation)

### `SkillGraphService`
- Calculates gap percentages per topic relative to the user's goal benchmark
- Updates `current_level` after an evaluation verdict
- Validates every read/write against the Zod schema — if the LLM writes a field that doesn't match the schema, it's caught here before reaching the DB
- Queries the Goal Knowledge Base to resolve `required_level` per topic

### `EvaluationService`
- Sequences questions from recall → application → depth
- Grades verdicts (Strong / Partial / Weak) and accumulates the session score
- Writes the evaluation result back to the Skill Graph via `SkillGraphService`

### `IngestionService`
- Extracts text from PDF (resume) and CSV (LeetCode export) uploads
- Chunks and embeds content via Voyage AI
- Writes embeddings to the Vector DB (episodic memory)
- Parses structured facts (solved counts, difficulty breakdown) into the Core Profile

### `AlertService`
- Checks pace deviation (actual problems solved vs. plan target)
- Detects inactivity (days since last session)
- Fires milestone alerts (gap closed, target hit early)
- Sends daily digest emails via Gmail SMTP

---

## Layer 3 — Data Layer (Repositories)

No business logic lives here. Repositories only read and write.

### Core Profile *(MongoDB · always injected)*
The user's goal, deadline, and availability. Small, stable, injected into every LLM call without retrieval. This is Layer 1 of the memory hierarchy.

```json
{
  "userId": "...",
  "goal": "20 LPA SWE role",
  "targetDate": "2026-08-01",
  "availability": { "weekdayHrs": 2, "weekendHrs": 4 }
}
```

### Skill Graph *(MongoDB · Zod-validated)*
Per-topic proficiency vs. the goal benchmark. Retrieved based on the topic being studied. This is Layer 2 of the memory hierarchy.

```json
{
  "topic": "graphs",
  "required_level": "hard",
  "current_level": "easy",
  "gap": "40%",
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
    "mentor_eval_score": "3/5"
  }
}
```

> ⚠️ **Schema is the contract.** The Zod schema for this document is the single source of truth shared by the LLM prompt (which writes to it), the service layer (which reads it), and the UI (which displays it). Change the Zod schema first — TypeScript types, DB migration, and prompt update follow.

### Episodic Memory *(Vector DB · Voyage AI)*
Session summaries and resolved doubts, semantically retrieved. This is Layer 3 of the memory hierarchy — retrieved only when relevant to the current topic.

### Prompt Store *(versioned files in `prompts/`)*
One prompt file per mode and evaluation level. Prompts are versioned (`v1`, `v2`, ...) and swappable without a code deploy. The `SessionService` selects the active version at runtime.

```
prompts/
  session/
    planning.v1.md
    topic.v1.md
    doubt.v1.md
  evaluation/
    recall.v1.md
    application.v1.md
    depth.v1.md
```

### Goal Knowledge Base *(curated benchmarks · periodic refresh)*
Stores `required_level` per topic per goal type (e.g., 20 LPA vs. FAANG). Sourced from interview data, refreshed periodically — not set once at onboarding.

---

## LLM Context Assembly (per call)

The LLM receives no persistent memory. On every call, the `SessionService` assembles:

```
System prompt (versioned, mode-specific)
  + Core Profile        ← always
  + Skill Graph nodes   ← topics relevant to current session
  + Episodic RAG        ← semantically similar past doubts/summaries
  + Conversation window ← last N messages
→ Claude API call
→ Response parsed by SessionService
→ Any skill graph updates written via SkillGraphService
```

---

## Key Architectural Decisions

| Decision | Rationale |
|---|---|
| MongoDB for Skill Graph (not relational) | The LLM generates the schema per user at runtime — different goals need different fields. MongoDB gives structure + flexibility. |
| Zod as layer boundary contract | Silent schema drift (LLM writes new field, UI doesn't expect it) is caught at runtime before poisoning the DB. |
| Prompt versioning in files, not DB | Prompts need diffs, review, and rollback — Git is the right tool, not a database table. |
| Voyage AI for embeddings | Higher retrieval quality for technical content (code, algo names) vs. OpenAI embeddings. Swappable via `IngestionService` interface. |
| Mode is auto-detected, never user-chosen | A good mentor doesn't ask you to categorize your question first. Mode shown passively as a read-only tag in the input bar. |

---

## Open Threads

- [ ] Ingestion pipeline — chunking strategy for resume PDFs (section-aware vs. fixed-size)
- [ ] Goal Knowledge Base refresh cadence — cron job or on-demand?
- [ ] Conflict resolution — what wins when LeetCode signal contradicts mentor eval score?
- [ ] Alert trigger model — cron (daily 8AM) vs. event-driven (on session end)
- [ ] Feature flag system — for rolling out new modes or evaluation changes safely
