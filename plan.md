# AI Mentor App — System Design Plan

A design document built from our discussion. The central idea: the LLM is the **brain**, and everything around it exists to give that brain the right memory and the right benchmark at the right time.

---

## 1. Core Features (Scope)

1. **Persistent memory** across sessions — structured and efficient, not a raw dump of history.
2. **Ingestion** of PDFs, images, text, and chunks (resume, progress exports, notes).
3. **Progress tracking** with proactive alerts and suggestions.
4. **Evaluation** of the user's actual proficiency, not just self-reported claims.

---

## 2. The Key Insight: Not All Memory Is Equal

A user's memory contains very different *kinds* of things, each with a different update frequency and recall urgency:

| Memory type | Example | Changes | Recall need |
|---|---|---|---|
| **Goal** | "Get 20 LPA in 3 months" | Rarely | Almost always relevant |
| **Skill assessment** | "Weak in graphs" | Over weeks | When studying related topic |
| **Session doubt** | "Confused about Dijkstra + negative edges" | Resolves fast | Semantically, when relevant |

This is why we **don't** dump all 200 sessions into the prompt — relevant context gets *positionally buried* and *attention-weighted down* by irrelevant noise (the "lost in the middle" problem). Retrieval must be selective.

---

## 3. Layered Memory Architecture

Instead of one flat vector store, memory is split into three layers:

**Layer 1 — Core Profile** *(always injected, no retrieval)*
Goals, timeline, overall level. Small, stable, always relevant.

**Layer 2 — Skill Graph** *(structured, queryable)*
Per-topic proficiency vs. the goal. Retrieved based on what the user is studying.

**Layer 3 — Episodic Memory** *(vector store + RAG)*
Specific doubts and session summaries. Semantically retrieved.

---

## 4. Hybrid Memory: The Storage Split

No single store is enough. Each layer maps to the tool that's good at its job:

```
Relational/Document DB  ──→  structured facts (gaps, scores, %)  ──┐
                                                                    ├──→ LLM reasons & responds
Vector DB               ──→  episodic memory (doubts, summaries)  ──┘

Web/Curated sources     ──→  goal curriculum (required level per topic)
```

- **MongoDB (document DB)** — stores the Skill Graph. Chosen over a rigid relational DB because the **model generates the schema per user at runtime**, and different goals (20 LPA vs. FAANG) need different fields. MongoDB gives structure *and* flexibility.
- **Vector DB** — semantic retrieval of past doubts and experiences.
- **LLM** — the reasoning engine. Has no memory of its own; the two DBs *are* its memory.

---

## 5. The Skill Graph Node

The crucial idea: **proficiency is measured relative to the goal**, not in absolute terms. You don't need to master graph theory for 20 LPA — you need to clear the interviews that come with it.

Example documents (note the schema differs by goal):

```json
// Goal: 20 LPA
{
  "topic": "graphs",
  "required_level": "medium",
  "current_level": "easy",
  "gap": "40%",
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
    "mentor_eval_score": "3/5"
  }
}

// Goal: FAANG
{
  "topic": "graphs",
  "required_level": "hard",
  "current_level": "medium",
  "gap": "30%",
  "system_design_overlap": true
}
```

---

## 6. Setting the Benchmark (`required_level`)

The model does **not** guess what a goal requires. It pulls from **curated, structured sources** (Glassdoor interview experiences, Naukri JDs, established prep sites) — higher signal-to-noise than random blogs — and stores the parsed result as a **Goal Knowledge Base**: the system's source of truth.

> Open item: refresh cadence. Interview patterns change, so this should be periodically re-fetched rather than set once.

---

## 7. Evaluation Loop (How Proficiency Is Measured)

Two signals combine:

1. **Passive** — LeetCode history (what's solved, at what difficulty, how fast).
2. **Active** — The mentor probes with questions. Question *type* determines what it learns:
   - Recall ("what is BFS?") — weak signal
   - Application ("which algorithm here and why?") — better
   - Depth ("can you beat O(V+E) for this case?") — reveals true level

The verdict updates the topic node's `current_level` and `gap` in MongoDB.

---

## 8. Proactive Mentoring

Memory isn't retrieved only on request — the system **reasons over it proactively**. When the user says "I'm learning stacks today," the mentor checks the goal + skill graph and can push back: *"Based on your plan, graphs is the bigger gap — start there."*

This drives the alerts and suggestions feature.

---

## 9. Onboarding (Day One)

No forms — a **conversational onboarding**. The model acts as an invested mentor and asks for what it needs:

> User: "Goal is 20 LPA, ready in 3 months."
> Model asks → user answers / uploads → model gathers context → generates schema → writes first MongoDB document.

What the model gathers: the goal, current progress, **resume (PDF)**, **progress exports (CSV/Excel)**. The developer is **not** in the loop for per-user schema decisions — the model owns that.

---

## 10. Ingestion Pipeline *(next thing to design)*

Onboarding depends on this. The LLM can't open files natively, so a pipeline is needed between "user uploads resume.pdf" and "model understands the user":

```
Upload → extract (PDF/CSV/image → text) → chunk → embed → store in Vector DB / parse into structured facts
```

> This is the open thread we stopped on — worth designing in detail next.

---

## Open Threads / To-Design

- [ ] Ingestion pipeline (extraction, chunking, embedding strategy)
- [ ] Goal Knowledge Base refresh cadence
- [ ] How alerts are triggered (cron? on-session? event-driven?)
- [ ] Conflict handling when LeetCode signal contradicts mentor-eval signal
- [ ] Privacy/storage of resume and personal data