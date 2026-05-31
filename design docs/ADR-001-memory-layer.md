# ADR-001: Three-Layer Memory Architecture for AI Mentor

**Status:** Accepted  
**Date:** 2026-05-23  
**Deciders:** Gopinath  

---

## Context

The AI Mentor is stateless by design — Claude has no memory between calls. Every LLM call must be given exactly the right context to reason well: the user's goal, where they stand today, and relevant past experiences. The question is how to store, structure, and retrieve that context efficiently.

Three competing forces shape the decision:

1. **The "lost in the middle" problem** — if all 200 past sessions are injected into the prompt, the goal stated at the top gets attention-weighted down by surrounding noise. The LLM answers correctly but stops connecting answers back to what actually matters.
2. **Different memory types decay at different rates** — a goal changes rarely; a topic proficiency score changes over weeks; a session doubt resolves in days. Treating them the same wastes retrieval precision.
3. **Scale is small, cost matters** — this is a single-user app in v1. The right architecture must be free or near-free, not enterprise-grade.

---

## Decision

Split memory into three layers with different storage strategies, all backed by a single MongoDB Atlas instance. Inject layers selectively per call rather than dumping everything.

| Layer | Name | Storage | Injection |
|---|---|---|---|
| L1 | Core Profile | MongoDB (document) | Always — every call |
| L2 | Skill Graph | MongoDB (document) | Always — filtered by topic |
| L3 | Episodic Memory | MongoDB Atlas Vector Search | Conditional — only when semantically needed |

---

## Options Considered

### Option A: Flat vector store (all memory in one vector DB)

Store everything — goals, skills, session summaries — as embeddings in a single vector DB (e.g., Pinecone). Retrieve top-K chunks per query.

| Dimension | Assessment |
|---|---|
| Complexity | Low to set up, high to tune |
| Cost | Pinecone free tier: 1 index, 100K vectors — sufficient for v1 |
| Retrieval precision | Poor for structured facts (goal, gap %) |
| Scalability | Good — vector DBs scale well |
| Team familiarity | Medium |

**Pros:** Simple mental model. One system to operate.  
**Cons:** Goals and proficiency scores are structured facts — they should be queried, not semantically searched. A 40% gap on graphs should be readable directly, not retrieved by cosine similarity from "user is weak at graphs." Also, vector DBs return K results regardless of relevance — there's no natural "this message doesn't need past context" signal.

### Option B: Relational DB + vector DB (two separate systems)

Store structured facts (L1, L2) in Postgres; store episodic memory (L3) in a dedicated vector DB like Pinecone.

| Dimension | Assessment |
|---|---|
| Complexity | High — two systems, two connection pools, two schemas to migrate |
| Cost | Pinecone free + Postgres (Railway ~$5/mo extra) |
| Retrieval precision | High — right tool for each job |
| Scalability | Excellent |
| Team familiarity | Low (Postgres + Pinecone adds ops surface) |

**Pros:** Clean separation. Best-in-class tooling for each layer.  
**Cons:** Overkill for a single-user v1. Adds operational complexity (two databases, two URIs in secrets, two failure modes). The retrieval quality advantage of Pinecone over MongoDB Atlas Vector Search is negligible at this corpus size (one user's sessions).

### Option C: MongoDB Atlas unified (structured + vector) — CHOSEN

Store all three layers in MongoDB Atlas. L1 and L2 use standard document queries. L3 uses Atlas Vector Search with metadata pre-filtering.

| Dimension | Assessment |
|---|---|
| Complexity | Low — one DB, one connection, one Atlas account |
| Cost | M0 free tier: 512MB storage, permanently free |
| Retrieval precision | High for L1/L2 (direct query); good for L3 (vector + filter) |
| Scalability | Good enough for v1; Pinecone migration path exists for v2 |
| Team familiarity | High — already using MongoDB |

**Pros:** One system to operate. Atlas Vector Search supports metadata pre-filtering alongside vector similarity — a single query can filter by `topic_category` and search by embedding simultaneously. IAM role auth (no credentials) already wired. No extra cost.  
**Cons:** Atlas Vector Search retrieval quality is slightly below dedicated Pinecone at large scale. Not an issue at v1 corpus size.

---

## Trade-off Analysis

The core trade-off is **operational simplicity vs. retrieval precision at scale**.

Option A (flat vector) trades precision for simplicity but gets the precision wrong — structured facts should be queried, not embedded. Rejecting it is not close.

Option B (two systems) trades simplicity for precision. The precision gain is real but measurable only at scale. At v1 (one user, hundreds of sessions), Atlas Vector Search and Pinecone produce effectively identical results. The operational cost of running two systems — two connection strings, two failure surfaces, two things to monitor — is not worth paying now.

Option C defers the Pinecone migration to when retrieval quality becomes a *measurable* problem, not a theoretical one. This is the right call.

The secondary trade-off is **context budget vs. retrieval completeness**. Injecting everything is not an option — 200 sessions would swamp the goal and bury the skill graph. The three-layer split solves this by assigning injection rules per layer: L1 and L2 are always injected (small, always relevant), L3 is conditionally retrieved (only when the message semantically needs past context). An intent pre-check using Haiku ("does this message need past session context? yes/no") gates the vector search. This adds ~100ms but keeps context clean on the majority of calls that don't need episodic recall.

---

## Architecture Detail

### Collections

```
users          → Layer 1: goal, deadline, level, availability, email prefs
skill_graph    → Layer 2: one doc per user per topic
                 { topic, required_level, current_level, gap, signals, last_studied }
sessions       → Layer 3: one doc per session
                 { summary (text), embedding (1536-dim), topic, topic_category,
                   type, date, skill_update }
alerts         → generated alerts + delivery status
goal_kb        → required levels per goal per topic (the benchmark source)
```

### Context assembly order (per call)

```
System prompt                     ~100 tok   (mentor persona, goal-aware instructions)
Layer 1 — Core Profile            ~200 tok   (always injected)
Layer 2 — Skill Graph             ~400 tok   (top gaps sorted by gap DESC)
Layer 3 — Episodic (conditional)  ~300 tok   (only if intent check returns yes)
Goal anchor reminder               ~50 tok   (goal + deadline + biggest gap, repeated at bottom)
Conversation history              ~500 tok   (rolling last 6 turns)
──────────────────────────────────────────
Total                           ~1,550 tok
```

### L3 retrieval

```
Haiku intent check: "Does this message need past session context? yes/no"
  │
  ├── no  → skip vector search (most messages)
  │
  └── yes → Atlas Vector Search
              pre-filter: { topic_category: <inferred> }
              vector: embed(user_message) via Voyage AI voyage-4-lite
              numCandidates: 50, limit: 5
              → inject top results into context
```

Pre-filtering by `topic_category` is critical — without it, "graph databases" (AWS topic) surfaces when the user asks about "graph algorithms" (DSA topic). Metadata filtering before vector similarity solves this cleanly.

### Embedding model

Voyage AI `voyage-4-lite` — 200M tokens/month free, 1536 dimensions, better retrieval quality than OpenAI text-embedding-3-small at the same price point. Already in the Anthropic ecosystem.

### Session end write (single LLM call)

At session end, one Sonnet call receives the full transcript and returns:

```json
{
  "narrative_summary": "3-5 sentences optimised for future semantic search",
  "skill_update": {
    "topic": "graphs",
    "current_level": "medium",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS"],
    "mock_score": "4/5"
  }
}
```

`narrative_summary` → embed via Voyage AI → upsert into `sessions` collection (L3).  
`skill_update` → upsert into `skill_graph` collection (L2), merge-only (preserves prior signals for fields not in current update).

---

## Consequences

**What becomes easier:**
- Retrieval for structured facts (gap %, required_level) is a direct MongoDB query — fast, deterministic, no embedding needed.
- The corpus stays small and clean — only session summaries are embedded, not raw transcripts.
- Single database means single connection, single IAM role, single failure surface.
- Context budget is predictable — L1 + L2 are fixed-size; L3 is gated by intent check.

**What becomes harder:**
- If retrieval quality degrades as session count grows (hundreds → thousands), migrating L3 to Pinecone requires re-embedding all summaries. This is a one-time data migration, not an ongoing burden.
- The intent pre-check adds a ~100ms Haiku call before the main Sonnet call on messages that need episodic context. Acceptable for v1; can be optimised later by running it in parallel.

**What to revisit:**
- Migrate `sessions` collection to Pinecone if Atlas Vector Search retrieval quality becomes a measurable problem (run evals before deciding, not on instinct).
- Add mid-session compression when sessions exceed ~10 turns — LLM summarises older turns in-place rather than dropping them from the rolling window.
- Re-evaluate L2 schema per goal type as more goal variants are onboarded. The LLM generates schema at onboarding, but the `skill_graph` collection currently has no schema validation — add JSON Schema validation once the common fields per goal type stabilise.

---

## Action Items

1. [ ] Implement Atlas Vector Search index on `sessions.embedding` with metadata fields `topic_category`, `type`, `date`
2. [ ] Build context assembler module — reads L1 + L2 from MongoDB, assembles prompt in correct order with goal anchor at bottom
3. [ ] Implement Haiku intent pre-check before L3 retrieval
4. [ ] Build session-end write flow — parse Sonnet JSON response, route `narrative_summary` to Voyage AI → Atlas, route `skill_update` to MongoDB upsert
5. [ ] Add MongoDB schema validation for `skill_graph` collection once common fields per goal stabilise (defer until 2–3 goal types onboarded)
6. [ ] Run retrieval quality evals at 50, 200, 500 session summaries — decide Pinecone migration threshold based on data, not instinct
