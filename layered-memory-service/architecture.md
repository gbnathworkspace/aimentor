# layered-memory-service — Architecture

## System Overview

```mermaid
graph TD
    subgraph Callers["External Callers"]
        B[LLM Backend / Main App]
    end

    subgraph API["FastAPI Service (AWS EC2)"]
        AUTH[X-API-Key Middleware]

        subgraph Routes["api/routes/"]
            R1[l1_profile.py\n/memory/profile]
            R2[l2_skill.py\n/memory/skill]
            R3[l3_episodic.py\n/memory/episodic]
        end

        subgraph CRUD["memory/"]
            C1[l1/crud.py\nProfile CRUD]
            C2[l2/crud.py\nSkill Graph CRUD]
            C3[l3/crud.py\nEpisodic CRUD]
            EMB[l3/embeddings.py\nVoyage Embedder]
        end

        DAL[dal/mongo.py\nMongoDB Connection]
    end

    subgraph Atlas["MongoDB Atlas"]
        COL1[(profiles\nL1 — one doc/user)]
        COL2[(skill_graph\nL2 — one doc/user/topic)]
        COL3[(sessions\nL3 — one doc/session)]
        VS[Atlas Vector Search\nembedding index]
    end

    VOYAGE[Voyage AI API\nvoyage-3]

    B -->|HTTP + X-API-Key| AUTH
    AUTH --> R1 & R2 & R3
    R1 --> C1
    R2 --> C2
    R3 --> C3
    C3 -->|POST /episodic — embed text| EMB
    EMB -->|1024-dim vector| VOYAGE
    VOYAGE -->|embedding| EMB
    C1 & C2 & C3 --> DAL
    DAL --> COL1 & COL2 & COL3
    COL3 --- VS
```

---

## Memory Layers

```mermaid
graph LR
    subgraph L1["L1 — Core Profile"]
        direction TB
        P1[goal]
        P2[deadline]
        P3[overall_level]
        P4[daily_availability]
    end

    subgraph L2["L2 — Skill Graph"]
        direction TB
        S1[topic]
        S2[required_level]
        S3[current_level]
        S4[gap %]
        S5[signals\nleetcode / eval score]
    end

    subgraph L3["L3 — Episodic Memory"]
        direction TB
        E1[session_id]
        E2[title + summary]
        E3[skill_update]
        E4[embedding vector\n1024 dims]
    end

    LLM[LLM Context\nWindow]

    L1 -->|always injected| LLM
    L2 -->|topic-based query| LLM
    L3 -->|lazy — only if needed\nsemantic vector search| LLM
```

---

## Request Flow — POST /memory/episodic (save session)

```mermaid
sequenceDiagram
    participant Caller as LLM Backend
    participant API as FastAPI
    participant CRUD as l3/crud.py
    participant EMB as embeddings.py
    participant OAI as Voyage AI API
    participant DB as MongoDB Atlas

    Caller->>API: POST /memory/episodic/{user_id}\n{ title, summary, topic, ... }
    API->>API: Verify X-API-Key
    API->>CRUD: save_session(user_id, data)
    CRUD->>EMB: embed(summary)
    EMB->>OAI: POST /embeddings\nvoyage-3
    OAI-->>EMB: [0.023, -0.041, ...] 1024 dims
    EMB-->>CRUD: embedding vector
    CRUD->>DB: insert document\n{ ...data, embedding: [...] }
    DB-->>CRUD: inserted_id
    CRUD-->>API: session_id
    API-->>Caller: 201 { session_id }
```

---

## Request Flow — POST /memory/episodic/{user_id}/search

```mermaid
sequenceDiagram
    participant Caller as LLM Backend
    participant API as FastAPI
    participant CRUD as l3/crud.py
    participant EMB as embeddings.py
    participant OAI as Voyage AI API
    participant DB as MongoDB Atlas Vector Search

    Caller->>API: POST /memory/episodic/{user_id}/search\n{ query: "struggled with graphs" }
    API->>API: Verify X-API-Key
    API->>CRUD: search_sessions(user_id, query)
    CRUD->>EMB: embed(query)
    EMB->>OAI: POST /embeddings\nvoyage-3
    OAI-->>EMB: query vector 1024 dims
    EMB-->>CRUD: query vector
    CRUD->>DB: $vectorSearch\n{ queryVector, limit: k }
    DB-->>CRUD: top-k session docs + scores
    CRUD-->>API: ranked sessions
    API-->>Caller: 200 [{ session, score }, ...]
```
