# Hybrid Storage

## Decision
Use MongoDB for structured data and a Vector DB for episodic memory.
No single store handles both jobs well.

## The Split

```
Relational/Document DB  →  structured facts (gaps, scores, dates)   ─┐
                                                                       ├→ LLM reasons
Vector DB               →  episodic memory (doubts, summaries)       ─┘
```

## Why MongoDB over a relational DB
The skill graph schema is generated per user at runtime by the LLM.
Different goals (20 LPA vs FAANG) need different fields.
A rigid relational schema can't accommodate this — MongoDB gives
structure and flexibility at the same time.

## Why Vector DB for episodic memory
Session summaries and doubts are free-form text.
Retrieval is semantic — "what did I struggle with in trees?" — not
a structured query. Embedding + cosine similarity is the right tool.

## Routing rule
```
Has a clear schema (scores, dates, difficulty, gaps)?  →  MongoDB
Free-form, needs semantic search?                       →  Vector DB
```

## Session data lives in both
At session end, two writes happen from one LLM call:
- Narrative summary → embedded → Vector DB
- Structured update (score, gap, weak_areas) → upserted → MongoDB

## LangChain as the Vector DB interface layer
`MongoDBAtlasVectorSearch` (from `langchain-mongodb`) is the interface
between FastAPI and MongoDB Atlas Vector Search.
It handles embedding generation, document storage, and retrieval in one abstraction.
Direct MongoDB queries are still used for all Layer 1 and Layer 2 reads/writes —
LangChain is only involved where vectors are stored or searched.
