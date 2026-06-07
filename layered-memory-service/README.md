# layered-memory-service

A production-grade HTTP microservice that gives LLM applications **persistent, structured memory** — without the calling service needing direct database access.

Built with FastAPI, MongoDB Atlas, and Voyage AI. Deployed on AWS EC2 with secrets managed via SSM Parameter Store.

---

## The Problem It Solves

LLM applications typically manage context in one of two ways:

1. **Stuff everything into the prompt** — gets expensive, hits token limits, buries important facts next to irrelevant ones.
2. **Single flat vector store** — retrieves everything by semantic similarity, which is great for episodes but terrible for facts that should always be present (like a user's goal or deadline).

This service introduces a third approach: **layered memory**, where each type of memory is stored and retrieved according to its own access pattern.

---

## Memory Architecture

```
┌────────────────────────────────────────┐
│             LLM Backend                │
│   (orchestration / main app)           │
└────────────────┬───────────────────────┘
                 │ HTTP  +  X-API-Key
                 ▼
┌────────────────────────────────────────────────────┐
│           layered-memory-service (FastAPI)          │
│                                                    │
│   ┌──────────────────────────────────────────┐    │
│   │  L1 — Core Profile   /memory/profile     │    │
│   │  Always-present facts: goal, deadline,   │    │
│   │  level, availability. Injected into      │    │
│   │  every prompt unconditionally.           │    │
│   └──────────────────────────────────────────┘    │
│                                                    │
│   ┌──────────────────────────────────────────┐    │
│   │  L2 — Skill Graph    /memory/skill       │    │
│   │  Per-topic knowledge state: current      │    │
│   │  level, required level, gap, signals.    │    │
│   │  Fetched deterministically by topic.     │    │
│   └──────────────────────────────────────────┘    │
│                                                    │
│   ┌──────────────────────────────────────────┐    │
│   │  L3 — Episodic Memory /memory/episodic   │    │
│   │  Session summaries with 1024-dim vector  │    │
│   │  embeddings. Retrieved lazily via        │    │
│   │  semantic search only when needed.       │    │
│   └──────────────────────────────────────────┘    │
└────────────────┬───────────────────────────────────┘
                 │
     ┌───────────▼───────────┐     ┌─────────────────┐
     │    MongoDB Atlas       │     │   Voyage AI API  │
     │  profiles              │     │  voyage-3 model  │
     │  skill_graph           │     │  1024-dim embed  │
     │  sessions + VSI        │     └─────────────────┘
     └───────────────────────┘
               ▲
         Atlas Vector Search Index
         (cosine similarity, pre-filtered
          by user_id and topic)
```

### Why three layers?

| Layer | What it stores | How it's retrieved | When to use |
|-------|---------------|-------------------|-------------|
| **L1** | Goal, deadline, skill level, availability | Always — no query needed | Every prompt |
| **L2** | Per-topic knowledge state and gaps | Exact lookup by `(user_id, topic)` | Session planning, difficulty calibration |
| **L3** | Full session summaries | Semantic vector search | Surfacing relevant past work |

The key insight: **not all memory needs semantic search**. A user's goal should be present every time, not retrieved when it happens to be similar to the current query. Mixing deterministic and semantic retrieval is what makes this effective.

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| API framework | **FastAPI** | Async-native, auto-generates OpenAPI docs, Pydantic validation |
| Database | **MongoDB Atlas** | Flexible document schema for `signals`; built-in vector search index |
| Embeddings | **Voyage AI `voyage-3`** | Outperforms OpenAI `text-embedding-3-large` on MTEB; 1024 dims keeps index lean |
| Secret management | **AWS SSM Parameter Store** | Secrets never touch env files in production; pulled at startup via EC2 instance role |
| Config validation | **pydantic-settings** | Missing required vars fail loudly at startup, not silently at request time |
| Deployment | **Docker + EC2 + systemd** | Reproducible builds; auto-restart on crash or reboot |

---

## Project Structure

```
layered-memory-service/
├── main.py                     # FastAPI app, router registration, DB lifespan
├── requirements.txt
├── Dockerfile
├── start.sh                    # Entrypoint for container (reads PORT, WORKERS, LOG_LEVEL)
├── layered-memory.service      # systemd unit for direct EC2 deployment
│
├── app/
│   ├── api/routes/
│   │   ├── l1_profile.py       # HTTP handlers for /memory/profile
│   │   ├── l2_skill.py         # HTTP handlers for /memory/skill
│   │   └── l3_episodic.py      # HTTP handlers for /memory/episodic
│   │
│   ├── memory/
│   │   ├── l1/crud.py          # Profile CRUD — upsert, partial update, delete
│   │   ├── l2/crud.py          # Skill node CRUD — keyed by (user_id, topic)
│   │   └── l3/
│   │       ├── crud.py         # Session CRUD + vector search pipeline
│   │       └── embeddings.py   # Voyage AI call wrapper — text → [1024 floats]
│   │
│   ├── dal/mongo.py            # DB connection, collection handles, index setup
│   │
│   ├── models/
│   │   ├── l1.py               # CoreProfile, ProfileUpdate (Pydantic)
│   │   ├── l2.py               # SkillNode, SkillUpdate (Pydantic)
│   │   └── l3.py               # EpisodicEntry, SearchQuery (Pydantic)
│   │
│   └── core/
│       ├── config.py           # All env vars in one place — local .env or AWS SSM
│       └── security.py         # X-API-Key dependency injected on every router
│
└── deployment/
    └── ec2-deployment-guide.md # Step-by-step Docker deployment on EC2
```

---

## API Reference

All endpoints require `X-API-Key: <secret>` in the request header.  
Interactive docs available at `http://localhost:8000/docs` when running locally.

### L1 — Core Profile

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/memory/profile` | Create profile (onboarding) |
| `GET` | `/memory/profile/{user_id}` | Fetch profile |
| `PUT` | `/memory/profile/{user_id}` | Partial update — only sent fields are changed |
| `DELETE` | `/memory/profile/{user_id}` | Delete profile |

**Create profile**
```bash
curl -X POST http://localhost:8000/memory/profile \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "gopinath",
    "goal": "20 LPA",
    "deadline": "Aug 2026",
    "overall_level": "beginner-intermediate",
    "daily_availability": "2hrs weekdays",
    "email": "user@example.com"
  }'
```

---

### L2 — Skill Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/memory/skill/{user_id}` | Create a topic node |
| `GET` | `/memory/skill/{user_id}` | List all topic nodes for a user |
| `GET` | `/memory/skill/{user_id}/{topic}` | Get a single topic node |
| `PUT` | `/memory/skill/{user_id}/{topic}` | Update node after a session or evaluation |
| `DELETE` | `/memory/skill/{user_id}/{topic}` | Remove a topic node |

**Create skill node**
```bash
curl -X POST http://localhost:8000/memory/skill/gopinath \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "graphs",
    "required_level": "medium",
    "current_level": "easy",
    "gap": "40%",
    "signals": {
      "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
      "mentor_eval_score": "3/5"
    }
  }'
```

The `signals` object is schema-free — the calling LLM defines it at onboarding and must remain consistent. This accommodates different goal types (placement, freelancing, upskilling) without requiring migrations.

---

### L3 — Episodic Memory

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/memory/episodic/{user_id}` | Save a session summary (triggers embedding generation) |
| `GET` | `/memory/episodic/{user_id}` | List sessions, paginated, newest first |
| `POST` | `/memory/episodic/{user_id}/search` | Semantic vector search over past sessions |
| `DELETE` | `/memory/episodic/{user_id}/{session_id}` | Delete a session |

**Save a session**
```bash
curl -X POST http://localhost:8000/memory/episodic/gopinath \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "graphs",
    "topic_category": "DSA",
    "type": "topic_session",
    "date": "2026-05-28",
    "title": "BFS/DFS revision",
    "summary": "User revised BFS and DFS. Strong on cycle detection. Struggled with negative weight cycles.",
    "skill_update": {
      "current_level": "medium",
      "weak_areas": ["negative weight cycles"],
      "strong_areas": ["BFS", "DFS"]
    }
  }'
```

The service embeds the `summary` via Voyage AI synchronously before storing — the response is not returned until both the embedding and the insert succeed.

**Semantic search**
```bash
curl -X POST http://localhost:8000/memory/episodic/gopinath/search \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "sessions where the user struggled with graph problems",
    "limit": 5,
    "topic": "graphs"
  }'
```

Returns sessions ranked by cosine similarity with a `score` field (0.0–1.0). The `user_id` filter is always applied at the query level — cross-user data leakage is impossible even if embeddings are highly similar.

---

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

No auth required. Used by load balancers and liveness probes.

---

## Local Development

```bash
# 1. Clone and set up environment
git clone https://github.com/gbnathworkspace/layered-memory-service.git
cd layered-memory-service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env
# edit .env — fill in MONGODB_URI, VOYAGE_API_KEY, MEMORY_SERVICE_API_KEY

# 3. Run
uvicorn main:app --reload --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Production Deployment (Docker on EC2)

See [`deployment/ec2-deployment-guide.md`](deployment/ec2-deployment-guide.md) for the full step-by-step.

**Quick version:**

```bash
# On the EC2 instance
git clone https://github.com/gbnathworkspace/layered-memory-service.git
cd layered-memory-service
docker build -t layered-memory-service .

docker run -d \
  --name layered-memory \
  --restart unless-stopped \
  -p 8000:8000 \
  -e APP_ENV=production \
  -e AWS_REGION=ap-south-1 \
  -e DB_SSM_PARAM_NAME=/mentorman/mongodb-uri \
  -e MONGODB_DB_NAME=layered_memory \
  layered-memory-service
```

In production mode (`APP_ENV=production`), the service fetches MongoDB URI, Voyage API key, and the internal API key directly from AWS SSM Parameter Store using the EC2 instance role — no credentials are passed as environment variables or baked into the image.

---

## Security Model

- **Authentication**: Every route is protected by a shared `X-API-Key` header validated against a value fetched from SSM at startup.
- **Internal-only**: This service must not be reachable from the public internet. The EC2 security group should allow inbound port 8000 only from the calling backend's private IP.
- **Secrets**: No credentials touch `.env` files in production. All secrets live in AWS SSM SecureString parameters (AES-256 encrypted at rest). boto3 uses the EC2 instance profile — no long-lived access keys anywhere.
- **User isolation**: Vector search always applies a `user_id` filter at the query level, enforced independently of application logic.

---

## MongoDB Atlas Setup

Before deploying, create the vector search index on the `sessions` collection:

```json
{
  "name": "session_embedding_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine" },
      { "type": "filter", "path": "user_id" },
      { "type": "filter", "path": "topic" }
    ]
  }
}
```

Regular indexes (`profiles.user_id`, `skill_graph.(user_id, topic)`, `sessions.session_id`) are created automatically at service startup via `dal/mongo.py`.

---

## Design Decisions

**Why synchronous embedding at write time?**  
Session saves happen once per session, not per message — so the ~200–400ms Voyage AI latency is acceptable. Async queuing would add infrastructure complexity (a queue + worker) for a write path that doesn't need sub-100ms response times.

**Why `signals` is schema-free on L2?**  
Different goal types (placement prep vs. freelancing vs. upskilling) require different tracking signals. Making `signals` a free-form `dict[str, Any]` means the calling LLM defines the schema at onboarding and updates it without any service-side migration.

**Why Voyage AI instead of OpenAI embeddings?**  
`voyage-3` consistently outperforms `text-embedding-3-large` on MTEB retrieval benchmarks. The 1024-dimension output keeps the Atlas vector index lean and search latency low. Upgrade path to `voyage-3-large` exists if retrieval quality degrades at scale.

**Why not a single vector store for everything?**  
A user's goal and deadline should appear in every prompt — not surface sometimes, depending on semantic similarity to the current query. Mixing deterministic facts with episodic retrieval leads to inconsistent LLM behaviour. The layer separation is the core design decision.
