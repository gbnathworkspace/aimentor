# layered-memory-service — System Design Plan

A reusable, standalone HTTP microservice that provides layered memory for LLM applications.
Any LLM backend can call this service over HTTP to read and write user memory — no direct DB access needed.

---

## Why This Exists

LLM apps need memory but not all memory is the same. Dumping everything into one flat store causes:
- Relevant context getting positionally buried (lost in the middle problem)
- Irrelevant noise getting attention-weighted equally with critical facts

This service solves that by splitting memory into three distinct layers, each with a different storage strategy and retrieval pattern.

---

## The Three Memory Layers

| Layer | What | Storage | Retrieval |
|---|---|---|---|
| L1 — Core Profile | Goal, deadline, level, availability | MongoDB `profiles` collection | Always injected, no retrieval needed |
| L2 — Skill Graph | Per-topic proficiency vs required level | MongoDB `skill_graph` collection | Topic-based structured query |
| L3 — Episodic Memory | Session summaries, doubts, experiences | MongoDB `sessions` + Atlas Vector Search | Semantic search (lazy — only when needed) |

---

## Key Design Decisions

### Single DB for all three layers
MongoDB Atlas handles L1 and L2 as regular documents and L3 via Atlas Vector Search.
No separate vector DB needed. At single-user scale the retrieval quality difference vs Pinecone is negligible.
Migrate L3 to Pinecone only if retrieval quality becomes a measurable problem at scale.

### Memory service is internal HTTP, not public
The service is called by other backend services over HTTP with a shared API key.
It is not exposed to the frontend or the public internet.

### Schema is caller-defined, not hardcoded
L2 skill graph schema is generated per user by the calling LLM at onboarding time.
Different goals (20 LPA vs FAANG) produce different topic sets and fields.
MongoDB's flexible document model accommodates this — no rigid relational schema.

### L3 retrieval is lazy
An intent pre-check determines whether a message needs past session context.
If not needed, vector search is skipped entirely — saves latency and keeps context clean.

---

## API Design

All routes require `X-API-Key` header.

### L1 — Core Profile

```
GET    /memory/profile/{user_id}         → fetch profile
POST   /memory/profile                   → create profile (onboarding)
PUT    /memory/profile/{user_id}         → update profile fields
DELETE /memory/profile/{user_id}         → delete profile
```

### L2 — Skill Graph

```
GET    /memory/skill/{user_id}           → all topics for user
GET    /memory/skill/{user_id}/{topic}   → single topic node
POST   /memory/skill/{user_id}           → create topic node
PUT    /memory/skill/{user_id}/{topic}   → update topic node (after eval/session)
DELETE /memory/skill/{user_id}/{topic}   → remove topic node
```

### L3 — Episodic Memory

```
GET    /memory/episodic/{user_id}                  → list sessions (paginated)
POST   /memory/episodic/{user_id}                  → save session summary + embed it
POST   /memory/episodic/{user_id}/search           → semantic vector search
DELETE /memory/episodic/{user_id}/{session_id}     → delete a session entry
```

---

## Data Shapes

### L1 — Core Profile document
```json
{
  "user_id": "gopinath",
  "goal": "20 LPA",
  "deadline": "Aug 2026",
  "overall_level": "beginner-intermediate",
  "daily_availability": "2hrs weekdays",
  "email": "user@gmail.com"
}
```

### L2 — Skill Graph document
```json
{
  "user_id": "gopinath",
  "topic": "graphs",
  "required_level": "medium",
  "current_level": "easy",
  "gap": "40%",
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
    "mentor_eval_score": "3/5"
  }
}
```

### L3 — Episodic session document
```json
{
  "session_id": "abc123",
  "user_id": "gopinath",
  "topic": "graphs",
  "topic_category": "DSA",
  "type": "topic_session",
  "date": "2026-05-22",
  "title": "BFS/DFS revision",
  "summary": "User revised BFS and DFS. Strong on cycle detection. Struggled with negative weight cycles.",
  "embedding": [0.023, -0.041, "...1024 dims"],
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
profiles       L1 — one doc per user
skill_graph    L2 — one doc per user per topic
sessions       L3 — one doc per session, with embedding vector
```

---

## Project Structure

```
layered-memory-service/
  app/
    api/
      routes/
        l1_profile.py       ← /memory/profile routes
        l2_skill.py         ← /memory/skill routes
        l3_episodic.py      ← /memory/episodic routes
    memory/
      l1/
        crud.py             ← profile read/write logic
      l2/
        crud.py             ← skill graph read/write logic
      l3/
        crud.py             ← episodic read/write logic
        embeddings.py       ← Voyage AI embedding calls
    dal/
      mongo.py              ← MongoDB connection
    models/
      l1.py                 ← CoreProfile pydantic models
      l2.py                 ← SkillNode pydantic models
      l3.py                 ← EpisodicEntry pydantic models
    core/
      config.py             ← env vars / settings
      security.py           ← API key verification
  main.py                   ← FastAPI app entry point
  requirements.txt
  .env.example
```

---

## Call Chain

```
Caller (main backend)
  → HTTP request with X-API-Key
    → FastAPI route (api/routes/)
      → memory CRUD (memory/l1|l2|l3/crud.py)
        → DAL (dal/mongo.py)
          → MongoDB Atlas
```

---

## Tech Stack

| Concern | Tech |
|---|---|
| Framework | FastAPI (Python) |
| Database | MongoDB Atlas |
| Vector Search | MongoDB Atlas Vector Search |
| Embeddings | Voyage AI voyage-3 (1024 dims) |
| Auth | Shared API key (X-API-Key header) |
| Hosting | AWS EC2 |

---

## Open Items

- [ ] Embedding generation — called at write time (POST /episodic) or async?
- [ ] Pagination strategy for GET /episodic/{user_id}
- [ ] Multi-user isolation — enforce user_id scoping at middleware level?
- [ ] Rate limiting on search endpoint
- [ ] Health check endpoint for ALB / nginx health probe
