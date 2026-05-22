# Tech Stack

## Final Stack

```
Layer              Tech                      Notes
──────────────────────────────────────────────────────────────────
Frontend           Next.js (App Router)      Chat UI, streaming
UI Library         shadcn/ui                 Composable, own the code
Auth               Clerk                     Drop-in Next.js auth
Backend            FastAPI (Python)          Ingestion + LLM orchestration
LLM (main)         Claude Sonnet 4.6         Reasoning + responses
LLM (lightweight)  Claude Haiku 4.5          Intent check, titles, drift
Embeddings         OpenAI text-embedding-3-small  Quality/cost balance
Database           MongoDB Atlas             Structured + vector (one DB)
Email              Gmail SMTP (Nodemailer)    Free, single user v1
Cron               Railway Cron              Daily alert trigger
File processing    PyMuPDF + pandas          PDF extraction + CSV parsing
Hosting (FE)       Vercel                    Zero config, free tier
Hosting (BE)       Railway                   FastAPI, $5/month, no cold starts
```

---

## Key Decisions

### One DB for structured + vector (MongoDB Atlas)
Atlas Vector Search handles Layer 3 (episodic memory) inside the
same database as Layer 1 and Layer 2. No dedicated Vector DB needed.

Single collection query can filter by metadata and search by vector simultaneously:
```json
{
  "$vectorSearch": {
    "index": "session_embedding_index",
    "path": "embedding",
    "queryVector": [...],
    "numCandidates": 50,
    "limit": 5,
    "filter": { "topic_category": "DSA" }
  }
}
```

Tradeoff: retrieval quality slightly below dedicated Pinecone at scale.
At this scale (one user's sessions) the difference is negligible.
Migrate to Pinecone only if retrieval quality becomes a measurable problem.

### Two Claude models
Sonnet 4.6 for all main reasoning — context assembly, responses, session summaries,
skill graph updates, onboarding, evaluation loop.

Haiku 4.5 for lightweight fast calls where quality doesn't need to be high:
- Intent check ("does this message need past context? yes/no")
- Session title generation
- Drift detection check
- Alert null check in daily cron

Keeps cost low without compromising response quality.

### FastAPI over Next.js API routes
Python is the right language for the ingestion pipeline:
- PyMuPDF for PDF extraction
- pandas for CSV parsing
- LangChain / direct Anthropic SDK for LLM orchestration
- Cleaner separation of concerns as complexity grows

Next.js handles the UI and thin session management layer.
FastAPI handles all heavy lifting.

### Clerk for auth
Drop-in Next.js integration. Handles email/password + Google OAuth.
User management UI out of the box. Free tier covers v1.

---

## Session Document Schema (MongoDB)

Structured fields + embedding vector in one document:
```json
{
  "session_id": "abc123",
  "user_id": "gopinath",
  "topic": "graphs",
  "topic_category": "DSA",
  "type": "topic_session",
  "date": "2026-05-22",
  "title": "BFS/DFS revision",
  "summary": "User revised BFS and DFS. Strong on cycle detection.
              Struggled with negative weight cycles.",
  "embedding": [0.023, -0.041, 0.019, "...1536 dimensions"],
  "skill_update": {
    "current_level": "medium",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS"]
  }
}
```

---

## MongoDB Collections

```
users              Core profile (Layer 1) + email preferences
skill_graph        Per-topic nodes (Layer 2), one doc per user per topic
sessions           Session transcripts + summaries + embeddings (Layer 3)
alerts             Generated alerts, delivery status
goal_kb            Goal Knowledge Base, required levels per goal per topic
```

---

## Free Tier Limits (v1)

```
MongoDB Atlas M0   512MB storage, shared cluster
Vercel             100GB bandwidth, serverless functions
Railway            $5/month (no free tier but cheapest paid)
Gmail SMTP         500 emails/day, free
Clerk              10,000 MAU
OpenAI Embeddings  Pay per use — negligible at this scale
```

---

## What to migrate in v2

```
MongoDB Atlas Vector Search → Pinecone   if retrieval quality degrades at scale
Railway Cron               → dedicated queue (BullMQ / Celery)   if alert volume grows
Gmail SMTP                 → Resend       when app opens to multiple users
```
