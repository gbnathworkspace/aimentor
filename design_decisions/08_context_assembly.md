# Context Assembly & Retrieval

## Decision
Build context from three layers before every LLM call.
Layer 3 is lazy — only retrieved when the message semantically needs it.

## Assembly order

```
┌──────────────────────────────────────────────┐
│  System prompt                    ~100 tok   │
├──────────────────────────────────────────────┤
│  Layer 1 — Core Profile           ~200 tok   │
│  goal, deadline, level, time                 │
├──────────────────────────────────────────────┤
│  Layer 2 — Skill Graph            ~400 tok   │
│  top gaps sorted by gap DESC                 │
├──────────────────────────────────────────────┤
│  Layer 3 — Episodic (if needed)   ~300 tok   │
│  semantically retrieved summaries            │
├──────────────────────────────────────────────┤
│  Goal anchor reminder             ~50 tok    │
│  (repeated at bottom, see goal anchoring)    │
├──────────────────────────────────────────────┤
│  Conversation history             ~500 tok   │
│  last 5-6 turns                              │
├──────────────────────────────────────────────┤
│  User message                                │
└──────────────────────────────────────────────┘
Total: ~1500 tokens
```

## Retrieval strategies by query type

```
Query type                         Retrieval
────────────────────────────────────────────────────
"what should I study today?"    →  L1 + L2 only
                                   No vector search needed

"explain IAM policies again"    →  L1 + L2 + L3 semantic search
                                   Finds past IAM session

"how was my AWS mock test?"     →  Metadata filter (topic=AWS,
                                   type=mock_test) + vector search
```

## Layer 3 conditional retrieval
An intent pre-check runs before the main LLM call:
"Does this message need past session context? yes/no"

- No  → skip vector search, save latency
- Yes → run vector search, inject top results

Adds ~100ms but keeps context clean when episodic memory isn't needed.

## Conversation history
Rolling window of last 6 turns. For long sessions (10+ turns),
mid-session compression kicks in: LLM summarizes older turns and
replaces raw transcript with the summary.

## Reranking
Not needed for v1. The corpus is small (one user's sessions).
Clean metadata filtering solves ambiguity better than a reranker.
The LLM reasoning over 5 retrieved chunks is the last-mile reranker.
