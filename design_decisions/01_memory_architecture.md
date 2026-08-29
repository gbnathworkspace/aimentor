# Memory Architecture

## Decision
Split memory into three distinct layers instead of one flat vector store.

## Why
Dumping all session history into context causes two problems:
- Relevant context gets positionally buried (lost in the middle problem)
- Irrelevant noise gets attention-weighted equally with critical facts

Not all memory has the same recall urgency or update frequency.

## The Three Layers

| Layer | What | Storage | Retrieval |
|---|---|---|---|
| Layer 1 | Core Profile — goal, deadline, level | MongoDB | Always injected, no retrieval |
| Layer 2 | Skill Graph — per-topic proficiency vs goal | MongoDB | Topic-based query |
| Layer 3 | Episodic Memory — doubts, session summaries | Vector DB | Semantic search |

## Layer 1 — Core Profile
Small, stable, always relevant. Injected into every context window unconditionally.
```json
{
  "goal": "System Design mastery",
  "deadline": "Aug 2026",
  "overall_level": "beginner-intermediate",
  "daily_availability": "2hrs weekdays"
}
```

## Layer 2 — Skill Graph
Structured, queryable. Retrieved based on what the user is studying.
Per-topic nodes with proficiency measured relative to the goal, not in absolute terms.

## Layer 3 — Episodic Memory
Free-form session summaries and doubts. Semantically retrieved when the user's
message requires past context (doubts, previous session recall).
Not retrieved by default — only when the message needs it.
