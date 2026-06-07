# layered-memory-service — Technical Documentation

> For developers and engineers integrating with or maintaining this service.

---

## Table of Contents

1. [Service Overview](#1-service-overview)
2. [Architecture](#2-architecture)
3. [Project Structure](#3-project-structure)
4. [Configuration & Environment](#4-configuration--environment)
5. [Authentication](#5-authentication)
6. [Database Design](#6-database-design)
7. [Memory Layer Internals](#7-memory-layer-internals)
8. [API Reference](#8-api-reference)
9. [Embedding Algorithm](#9-embedding-algorithm)
10. [Vector Search Internals](#10-vector-search-internals)
11. [Internal Call Chain](#11-internal-call-chain)
12. [Pydantic Models](#12-pydantic-models)
13. [Error Handling](#13-error-handling)
14. [Deployment](#14-deployment)
15. [Open Engineering Questions](#15-open-engineering-questions)

---

## 1. Service Overview

`layered-memory-service` is an internal HTTP microservice. It provides persistent, structured memory for LLM applications — without the calling service needing direct database access.

The core insight it encodes: **not all memory is equal**. A user's goal and deadline (always relevant) should not be stored and retrieved the same way as a session from 3 weeks ago (rarely relevant, content-dependent). Mixing them into a flat store causes two failure modes:

- **Lost-in-the-middle**: relevant context gets positionally buried in a long prompt.
- **Noise injection**: irrelevant past sessions get equal attention-weight to critical facts.

The service separates memory into three layers, each with a dedicated storage strategy and retrieval pattern. The calling LLM backend assembles its context window by pulling from each layer according to its own logic.

---

## 2. Architecture

```
┌──────────────────────────────────┐
│         LLM Backend              │
│  (main app / orchestration svc)  │
└────────────────┬─────────────────┘
                 │ HTTP + X-API-Key
                 ▼
┌──────────────────────────────────────────────────┐
│              FastAPI Service (AWS EC2)            │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │         API Key Middleware               │    │
│  └──────────────┬──────────────────────────┘    │
│                 │                                │
│  ┌──────────────▼──────────────────────────┐    │
│  │             Routes Layer                 │    │
│  │  l1_profile.py  l2_skill.py  l3_episodic│    │
│  └──────────────┬──────────────────────────┘    │
│                 │                                │
│  ┌──────────────▼──────────────────────────┐    │
│  │             CRUD Layer                   │    │
│  │  l1/crud.py  l2/crud.py  l3/crud.py     │    │
│  │                     + embeddings.py      │    │
│  └──────────────┬──────────────────────────┘    │
│                 │                                │
│  ┌──────────────▼──────────────────────────┐    │
│  │         DAL  (dal/mongo.py)              │    │
│  └──────────────┬──────────────────────────┘    │
└─────────────────┼────────────────────────────────┘
                  │
       ┌──────────▼──────────┐        ┌────────────────┐
       │    MongoDB Atlas     │        │  Voyage AI API │
       │  profiles            │        │   voyage-3     │
       │  skill_graph         │        │  (1024 dims)   │
       │  sessions ──► VSI   │        └────────────────┘
       └─────────────────────┘
                  ▲ vector search index (VSI)
                  │ used only on POST /episodic/{id}/search
```

**Key boundary**: The service is internal only. It must not be reachable from the public internet or the frontend. The calling backend holds the API key and proxies all memory operations.

---

## 3. Project Structure

```
layered-memory-service/
│
├── main.py                    # FastAPI app instantiation, router registration, lifespan
│
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── l1_profile.py  # Route handlers for /memory/profile
│   │       ├── l2_skill.py    # Route handlers for /memory/skill
│   │       └── l3_episodic.py # Route handlers for /memory/episodic
│   │
│   ├── memory/
│   │   ├── l1/
│   │   │   └── crud.py        # Profile create / read / update / delete
│   │   ├── l2/
│   │   │   └── crud.py        # Skill node create / read / update / delete
│   │   └── l3/
│   │       ├── crud.py        # Episodic session create / read / search / delete
│   │       └── embeddings.py  # Voyage AI embedding call wrapper
│   │
│   ├── dal/
│   │   └── mongo.py           # MongoDB client, collection accessors, index setup
│   │
│   ├── models/
│   │   ├── l1.py              # Pydantic models: CoreProfile, ProfileUpdate
│   │   ├── l2.py              # Pydantic models: SkillNode, SkillUpdate
│   │   └── l3.py              # Pydantic models: EpisodicEntry, SearchQuery
│   │
│   └── core/
│       ├── config.py          # Settings via pydantic-settings (reads .env)
│       └── security.py        # API key dependency for FastAPI routes
│
├── requirements.txt
├── .env.example
├── plan.md
├── architecture.md
└── TECHNICAL_DOCS.md          # ← this file
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | Boot FastAPI, register routers, manage DB lifespan |
| `api/routes/` | HTTP interface — parse requests, call CRUD, return responses |
| `memory/*/crud.py` | Business logic — query construction, document assembly |
| `memory/l3/embeddings.py` | Isolated Voyage AI call — takes a string, returns a float list |
| `dal/mongo.py` | Single source of truth for the DB connection and collection handles |
| `models/` | Pydantic schemas for request validation and response serialization |
| `core/config.py` | All env vars in one place — nothing else reads `os.environ` directly |
| `core/security.py` | FastAPI dependency that enforces `X-API-Key` on every route |

---

## 4. Configuration & Environment

All configuration is read from environment variables. In local development, place these in a `.env` file. In production on EC2, set them in `/etc/layered-memory.env` (loaded by the systemd unit) or export them in the shell before running.

```env
# .env.example

MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
MONGODB_DB_NAME=layered_memory

VOYAGE_API_KEY=pa-...

MEMORY_SERVICE_API_KEY=your-internal-shared-secret

# Optional
LOG_LEVEL=INFO
```

`core/config.py` uses `pydantic-settings` to parse and validate these at startup:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongodb_uri: str
    mongodb_db_name: str = "layered_memory"
    voyage_api_key: str
    memory_service_api_key: str
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

If any required variable is missing, the app will fail at startup with a clear validation error — not silently at request time.

---

## 5. Authentication

Every route is protected by a shared API key passed in the `X-API-Key` request header.

**Implementation** (`core/security.py`):

```python
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.memory_service_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
```

This is injected as a FastAPI dependency on every router:

```python
router = APIRouter(dependencies=[Depends(verify_api_key)])
```

**Security model**: The key is a symmetric shared secret between this service and its callers. It is never sent to the frontend. Rotate by updating the env var and redeploying; all callers must update simultaneously or requests will fail with `403`.

---

## 6. Database Design

### Collections

| Collection | Layer | Cardinality | Primary key |
|---|---|---|---|
| `profiles` | L1 | 1 doc per user | `user_id` |
| `skill_graph` | L2 | 1 doc per user per topic | `(user_id, topic)` |
| `sessions` | L3 | 1 doc per session | `session_id` (UUID) |

### Indexes

```javascript
// profiles
db.profiles.createIndex({ "user_id": 1 }, { unique: true })

// skill_graph
db.skill_graph.createIndex({ "user_id": 1, "topic": 1 }, { unique: true })

// sessions
db.sessions.createIndex({ "user_id": 1 })
db.sessions.createIndex({ "session_id": 1 }, { unique: true })

// Atlas Vector Search index (created via Atlas UI or API, not driver)
// Index name: "session_embedding_index"
// Field: "embedding"
// Dimensions: 1024
// Similarity: cosine
```

The vector search index is an **Atlas Search index**, not a regular MongoDB index. It must be created separately via the Atlas UI or the Atlas Search API before the `/search` endpoint will work.

### Document Schemas

#### `profiles` — L1

```json
{
  "_id": "<ObjectId>",
  "user_id": "gopinath",
  "goal": "20 LPA",
  "deadline": "Aug 2026",
  "overall_level": "beginner-intermediate",
  "daily_availability": "2hrs weekdays",
  "email": "user@gmail.com",
  "created_at": "2026-05-22T10:00:00Z",
  "updated_at": "2026-05-22T10:00:00Z"
}
```

#### `skill_graph` — L2

```json
{
  "_id": "<ObjectId>",
  "user_id": "gopinath",
  "topic": "graphs",
  "required_level": "medium",
  "current_level": "easy",
  "gap": "40%",
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
    "mentor_eval_score": "3/5"
  },
  "created_at": "2026-05-22T10:00:00Z",
  "updated_at": "2026-05-22T10:00:00Z"
}
```

`signals` is a free-form nested object. The calling LLM defines its schema at onboarding time — there is no enforced sub-schema. This accommodates different goal types (placement, freelancing, upskilling) that require different signals.

#### `sessions` — L3

```json
{
  "_id": "<ObjectId>",
  "session_id": "uuid-v4-string",
  "user_id": "gopinath",
  "topic": "graphs",
  "topic_category": "DSA",
  "type": "topic_session",
  "date": "2026-05-22",
  "title": "BFS/DFS revision",
  "summary": "User revised BFS and DFS. Strong on cycle detection. Struggled with negative weight cycles.",
  "embedding": [0.023, -0.041, "... 1024 floats total"],
  "skill_update": {
    "current_level": "medium",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS"]
  },
  "created_at": "2026-05-22T10:00:00Z"
}
```

The `embedding` field stores the 1024-dimensional vector produced by Voyage AI `voyage-3` from the `summary` field. It is written at POST time and never updated — if a summary changes, delete and re-create the session document.

---

## 7. Memory Layer Internals

### L1 — Core Profile

**Purpose**: Always-present user context. Injected into every LLM prompt unconditionally.

**Retrieval strategy**: No retrieval. The calling backend fetches the profile once and prepends it to every system prompt. There is no filtering or ranking.

**Write behaviour**: `PUT` uses MongoDB `$set` — only fields present in the request body are updated. Missing fields are left unchanged. Callers should never send a full document to PUT; always send only changed fields.

---

### L2 — Skill Graph

**Purpose**: Structured per-topic knowledge state. Used to personalize what the LLM teaches and how hard.

**Retrieval strategy**: Deterministic lookup by `(user_id, topic)`. No semantic search. The calling backend decides which topic to fetch based on the current session's subject.

**Schema flexibility**: The `signals` sub-object is defined by the calling LLM during onboarding (`POST /skill/{user_id}`). MongoDB does not enforce a schema on it. This means:
- Different users can have different signal keys.
- The calling LLM must remain consistent with the schema it originally created.
- There is no migration needed when signal definitions change — just update the doc.

**Gap calculation**: `gap` is a string (e.g., `"40%"`) computed and written by the calling LLM, not by this service. This service stores and returns it as-is.

---

### L3 — Episodic Memory

**Purpose**: Long-term session history. Retrieved lazily via semantic search when current context requires it.

**Write path**:
1. Caller POSTs a session summary (text).
2. Service calls Voyage AI `voyage-3` with the summary text.
3. Returns a 1024-dim float vector.
4. Service stores the full document including the embedding vector.
5. Atlas Vector Search indexes the vector asynchronously (seconds after write).

**Read path — list**: Paginated fetch of session documents sorted by `created_at` descending. No vector search involved.

**Read path — search**: Semantic vector search. See [Section 10](#10-vector-search-internals).

**Lazy retrieval contract**: This service does not decide when to search. The calling LLM backend is responsible for:
1. Determining if the user's current message needs past context (intent pre-check).
2. Calling `POST /episodic/{user_id}/search` only when needed.
3. Injecting the returned summaries into the prompt.

This keeps latency low and the context window clean for messages that don't need history.

---

## 8. API Reference

All endpoints require: `X-API-Key: <secret>` header.  
Base URL: `http://<ec2-ip-or-domain>:8000` (put nginx in front for TLS)

---

### L1 — Core Profile

#### `GET /memory/profile/{user_id}`

Fetch the profile for a user.

**Path params**: `user_id` — string identifier for the user.

**Response `200`**:
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

**Response `404`**: User not found.

---

#### `POST /memory/profile`

Create a new profile. Called once at onboarding.

**Request body**:
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

**Response `201`**:
```json
{ "user_id": "gopinath", "created": true }
```

**Response `409`**: Profile already exists for this `user_id`.

---

#### `PUT /memory/profile/{user_id}`

Partial update. Send only the fields to change.

**Request body** (all fields optional):
```json
{
  "goal": "FAANG",
  "daily_availability": "3hrs weekdays"
}
```

**Response `200`**:
```json
{ "user_id": "gopinath", "updated": true }
```

---

#### `DELETE /memory/profile/{user_id}`

Delete a user's profile. Does not cascade — skill graph and session docs must be deleted separately if full user deletion is needed.

**Response `200`**:
```json
{ "user_id": "gopinath", "deleted": true }
```

---

### L2 — Skill Graph

#### `GET /memory/skill/{user_id}`

Returns all topic nodes for a user.

**Response `200`**:
```json
[
  {
    "user_id": "gopinath",
    "topic": "graphs",
    "required_level": "medium",
    "current_level": "easy",
    "gap": "40%",
    "signals": { "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 } }
  },
  {
    "user_id": "gopinath",
    "topic": "dynamic_programming",
    ...
  }
]
```

---

#### `GET /memory/skill/{user_id}/{topic}`

Returns a single topic node.

**Path params**: `topic` — exact topic string (e.g., `graphs`, `dynamic_programming`).

**Response `200`**: Single skill node object.  
**Response `404`**: Topic not found for user.

---

#### `POST /memory/skill/{user_id}`

Create a new topic node. Called during onboarding when the LLM generates the user's skill graph.

**Request body**:
```json
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
```

**Response `201`**:
```json
{ "user_id": "gopinath", "topic": "graphs", "created": true }
```

**Response `409`**: Topic node already exists.

---

#### `PUT /memory/skill/{user_id}/{topic}`

Update a topic node after a session or evaluation. Send only changed fields.

**Request body** (all optional):
```json
{
  "current_level": "medium",
  "gap": "20%",
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 8, "hard": 1 },
    "mentor_eval_score": "4/5"
  }
}
```

**Response `200`**:
```json
{ "user_id": "gopinath", "topic": "graphs", "updated": true }
```

---

#### `DELETE /memory/skill/{user_id}/{topic}`

Remove a topic node from the skill graph.

**Response `200`**:
```json
{ "user_id": "gopinath", "topic": "graphs", "deleted": true }
```

---

### L3 — Episodic Memory

#### `GET /memory/episodic/{user_id}`

List session documents for a user, newest first.

**Query params**:

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | `20` | Max results per page |
| `offset` | int | `0` | Number of documents to skip |
| `topic` | string | — | Optional filter by topic |

**Response `200`**:
```json
{
  "total": 47,
  "limit": 20,
  "offset": 0,
  "results": [
    {
      "session_id": "abc123",
      "user_id": "gopinath",
      "topic": "graphs",
      "topic_category": "DSA",
      "type": "topic_session",
      "date": "2026-05-22",
      "title": "BFS/DFS revision",
      "summary": "...",
      "skill_update": { ... }
    }
  ]
}
```

Note: `embedding` is excluded from list responses to keep payload size manageable.

---

#### `POST /memory/episodic/{user_id}`

Save a session summary. Triggers embedding generation synchronously before storing.

**Request body**:
```json
{
  "topic": "graphs",
  "topic_category": "DSA",
  "type": "topic_session",
  "date": "2026-05-22",
  "title": "BFS/DFS revision",
  "summary": "User revised BFS and DFS. Strong on cycle detection. Struggled with negative weight cycles.",
  "skill_update": {
    "current_level": "medium",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS"]
  }
}
```

**Internally**: `summary` is sent to Voyage AI for embedding. The resulting 1024-dim vector is stored alongside the document. This adds ~200–400ms latency to the write.

**Response `201`**:
```json
{ "session_id": "uuid-v4-string", "created": true }
```

---

#### `POST /memory/episodic/{user_id}/search`

Semantic vector search over past sessions.

**Request body**:
```json
{
  "query": "struggled with graph traversal and tree problems",
  "limit": 5,
  "topic": "graphs"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Natural language search text |
| `limit` | int | no (default 5) | Max number of results |
| `topic` | string | no | Pre-filter by topic before vector search |

**Internally**: `query` is embedded via Voyage AI, then `$vectorSearch` runs against the `sessions` collection using the `session_embedding_index`. Results are ranked by cosine similarity.

**Response `200`**:
```json
[
  {
    "session_id": "abc123",
    "title": "BFS/DFS revision",
    "summary": "...",
    "topic": "graphs",
    "date": "2026-05-22",
    "score": 0.94
  }
]
```

`score` is the cosine similarity (0.0–1.0). Higher is more semantically similar.

---

#### `DELETE /memory/episodic/{user_id}/{session_id}`

Delete a single session document by its `session_id`.

**Response `200`**:
```json
{ "session_id": "abc123", "deleted": true }
```

---

### Health Check

#### `GET /health`

No auth required. Used by nginx / ALB for liveness probing.

**Response `200`**:
```json
{ "status": "ok" }
```

---

## 9. Embedding Algorithm

Embeddings are generated in `memory/l3/embeddings.py`.

**Model**: `voyage-3` (Voyage AI)  
**Output dimensions**: 1024  
**Input**: The `summary` field of an episodic session (plain text, typically 50–300 words)  
**Similarity metric**: Cosine similarity (configured on the Atlas vector index)

```python
import voyageai
from app.core.config import settings

client = voyageai.AsyncClient(api_key=settings.voyage_api_key)

async def embed(text: str) -> list[float]:
    response = await client.embed(
        texts=[text],
        model="voyage-3"
    )
    return response.embeddings[0]  # list of 1024 floats
```

**Why `voyage-3`**:
- State-of-the-art retrieval quality — outperforms OpenAI text-embedding-3-large on MTEB benchmarks.
- 1024 dimensions keeps the Atlas vector index lean and search latency low.
- Cost-effective for high write volume (each session save = 1 embedding call).
- Upgrade to `voyage-3-large` only if retrieval quality degrades at scale (same 1024 dims, stronger model).

**Embedding is synchronous at write time**: The POST `/episodic` response is not returned until the embedding is complete and the document is stored. This is simpler than an async queue and acceptable given that session saves are low-frequency (once per session, not per message).

---

## 10. Vector Search Internals

### Atlas Vector Search Index

Must be created once via the Atlas UI or API before the search endpoint works.

**Index definition**:
```json
{
  "name": "session_embedding_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "path": "embedding",
        "numDimensions": 1024,
        "similarity": "cosine"
      },
      {
        "type": "filter",
        "path": "user_id"
      },
      {
        "type": "filter",
        "path": "topic"
      }
    ]
  }
}
```

`user_id` and `topic` are declared as filter fields so they can be used in pre-filter clauses without degrading search performance.

### `$vectorSearch` Query Construction

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": "session_embedding_index",
            "path": "embedding",
            "queryVector": query_embedding,   # 1024-dim float list
            "numCandidates": limit * 10,      # oversample, then re-rank
            "limit": limit,
            "filter": {
                "user_id": {"$eq": user_id},
                # "topic": {"$eq": topic}  # added only if topic param is provided
            }
        }
    },
    {
        "$project": {
            "session_id": 1,
            "title": 1,
            "summary": 1,
            "topic": 1,
            "date": 1,
            "skill_update": 1,
            "score": {"$meta": "vectorSearchScore"},
            "embedding": 0   # exclude — large field, not needed in response
        }
    }
]
```

**`numCandidates`**: Set to `limit * 10` (minimum 20). Atlas ANN search retrieves `numCandidates` approximate neighbours then re-ranks by exact cosine similarity to return the top `limit`. Higher `numCandidates` = better recall at the cost of latency.

**User isolation**: `user_id` filter is always applied — a user can never receive another user's sessions, even if their embeddings are highly similar. This is enforced at the query level, not just the application level.

---

## 11. Internal Call Chain

### Write — `POST /memory/episodic/{user_id}`

```
HTTP POST /memory/episodic/gopinath
  │
  ├─ security.py: verify X-API-Key → 403 if invalid
  │
  ├─ l3_episodic.py (route handler)
  │   └─ validates request body against EpisodicEntry pydantic model
  │
  ├─ l3/crud.py: save_session(user_id, data)
  │   ├─ generates session_id = uuid4()
  │   ├─ calls embeddings.embed(data.summary) → awaits Voyage AI
  │   └─ assembles full document dict with embedding + timestamps
  │
  ├─ dal/mongo.py: get_sessions_collection().insert_one(doc)
  │
  └─ returns { session_id, created: true } → HTTP 201
```

### Read — `POST /memory/episodic/{user_id}/search`

```
HTTP POST /memory/episodic/gopinath/search
  │
  ├─ security.py: verify X-API-Key
  │
  ├─ l3_episodic.py (route handler)
  │   └─ validates SearchQuery body
  │
  ├─ l3/crud.py: search_sessions(user_id, query, limit, topic)
  │   ├─ calls embeddings.embed(query.query) → awaits Voyage AI
  │   ├─ builds $vectorSearch pipeline with user_id filter
  │   └─ runs aggregate() on sessions collection
  │
  └─ returns ranked list of session dicts → HTTP 200
```

---

## 12. Pydantic Models

### `models/l1.py`

```python
from pydantic import BaseModel
from typing import Optional

class CoreProfile(BaseModel):
    user_id: str
    goal: str
    deadline: str
    overall_level: str
    daily_availability: str
    email: str

class ProfileUpdate(BaseModel):
    goal: Optional[str] = None
    deadline: Optional[str] = None
    overall_level: Optional[str] = None
    daily_availability: Optional[str] = None
    email: Optional[str] = None
```

### `models/l2.py`

```python
from pydantic import BaseModel
from typing import Optional, Any

class SkillNode(BaseModel):
    topic: str
    required_level: str
    current_level: str
    gap: str
    signals: dict[str, Any] = {}

class SkillUpdate(BaseModel):
    required_level: Optional[str] = None
    current_level: Optional[str] = None
    gap: Optional[str] = None
    signals: Optional[dict[str, Any]] = None
```

### `models/l3.py`

```python
from pydantic import BaseModel
from typing import Optional, Any

class SkillUpdateSnapshot(BaseModel):
    current_level: Optional[str] = None
    weak_areas: list[str] = []
    strong_areas: list[str] = []

class EpisodicEntry(BaseModel):
    topic: str
    topic_category: str
    type: str
    date: str
    title: str
    summary: str
    skill_update: Optional[SkillUpdateSnapshot] = None

class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    topic: Optional[str] = None
```

---

## 13. Error Handling

All errors return a JSON body of the form:
```json
{ "detail": "human-readable message" }
```

| HTTP Status | When |
|---|---|
| `400 Bad Request` | Request body fails pydantic validation |
| `403 Forbidden` | Missing or invalid `X-API-Key` |
| `404 Not Found` | Document not found for given `user_id` / `topic` / `session_id` |
| `409 Conflict` | Attempt to create a resource that already exists |
| `500 Internal Server Error` | Unhandled exception (MongoDB error, Voyage AI timeout, etc.) |
| `503 Service Unavailable` | MongoDB connection failed at startup |

**Voyage AI failures**: If the embedding call fails (rate limit, network error), the session write returns `500`. The caller should retry. The document is not partially written — the insert only happens after the embedding succeeds.

---

## 14. Deployment

### AWS EC2

#### One-time EC2 setup

```bash
# 1. SSH into the instance
ssh -i <key.pem> ec2-user@<ec2-ip>

# 2. Install Python 3.11+
sudo dnf install python3.11 python3.11-pip -y   # Amazon Linux 2023
# or: sudo apt install python3.11 python3.11-venv -y   # Ubuntu

# 3. Clone the repo
git clone https://github.com/gbnathworkspace/layered-memory-service.git
cd layered-memory-service

# 4. Create virtualenv and install deps
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Write production env vars (non-secret ones; secrets come from SSM)
sudo tee /etc/layered-memory.env <<EOF
APP_ENV=production
AWS_REGION=ap-south-1
DB_SSM_PARAM_NAME=/mentorman/mongodb-uri
MONGODB_DB_NAME=layered_memory
LOG_LEVEL=INFO
PORT=8000
EOF
sudo chmod 600 /etc/layered-memory.env

# 6. Install and enable the systemd service
sudo cp layered-memory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable layered-memory
sudo systemctl start layered-memory

# 7. Check it's running
sudo systemctl status layered-memory
curl http://localhost:8000/health
```

#### IAM permissions required

The EC2 instance profile must have an IAM policy allowing:

```json
{
  "Effect": "Allow",
  "Action": "ssm:GetParameter",
  "Resource": [
    "arn:aws:ssm:ap-south-1:<account-id>:parameter/voyageapikey",
    "arn:aws:ssm:ap-south-1:<account-id>:parameter/mentorman/mongodb-uri",
    "arn:aws:ssm:ap-south-1:<account-id>:parameter/layered-memory-service/api-key"
  ]
}
```

boto3 picks up the instance profile credentials automatically — no `AWS_ACCESS_KEY_ID` needed.

#### Security group

Open inbound port `8000` (or `443` if nginx with TLS is in front) only to the private IP of the calling backend — never to `0.0.0.0/0`.

#### Updating the service

```bash
cd /home/ec2-user/layered-memory-service
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart layered-memory
```

---

### MongoDB Atlas Setup

1. Create an Atlas cluster (M0 free tier is sufficient for development).
2. Create a database named `layered_memory` (or match `MONGODB_DB_NAME`).
3. Create the three collections: `profiles`, `skill_graph`, `sessions`.
4. Create the regular indexes (the app does this automatically in `dal/mongo.py` at startup).
5. Create the Vector Search index named `session_embedding_index` as defined in Section 10.
6. Whitelist the EC2 instance's Elastic IP in Atlas Network Access.

---

### Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env values
uvicorn main:app --reload --port 8000
```

API will be available at `http://localhost:8000`.  
Interactive docs (Swagger UI): `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

---

## 15. Open Engineering Questions

These are unresolved design decisions that will need answers before production:

| Question | Options | Recommendation |
|---|---|---|
| ~~Embedding at write time vs async~~ | **Decided: synchronous at write time.** Session saves are once-per-session, not per-message. If Voyage AI fails or times out, log the error and return `500` — caller can retry. Data loss risk is accepted at current scale. Revisit if session save reliability becomes a problem. | — |
| Pagination strategy for `GET /episodic` | Offset-based (simple) vs cursor-based (stable under concurrent writes) | **Offset** for now. Switch to cursor if users accumulate >500 sessions. |
| Multi-user isolation enforcement | Application-level (current) vs middleware-level `user_id` injection | Consider middleware injection if the number of callers grows — reduces risk of caller bugs leaking cross-user data. |
| Rate limiting on `/search` | Per-user limit in middleware (slowapi) vs upstream API gateway | Add `slowapi` rate limiting on `/search` before any production traffic — it triggers a Voyage AI call on every request. |
| Full user deletion cascade | Manual (caller deletes profile → skills → sessions) vs single endpoint | Add `DELETE /memory/user/{user_id}` that cascades all three collections atomically if GDPR or data retention is a concern. |
