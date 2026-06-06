# Backend Requirements — What the Frontend Needs and Why

## Current Problem
`mentorman-app/app/api/mentor/route.ts` calls Anthropic directly and fetches memory
from the backend itself. This violates the architecture: the backend should own ALL
LLM orchestration + context assembly. The frontend's `/api/mentor` route should be a
thin proxy — nothing more.

---

## Already Working (Memory Endpoints)
These are in `mentorman-app/lib/mentorman-api.ts` and the frontend already uses them:

```
/memory/profile/{userId}     GET / POST / PUT / DELETE
/memory/skill/{userId}       GET / POST
/memory/skill/{userId}/{topic}  GET / PUT / DELETE
/memory/episodic/{userId}    GET / POST (with ?limit&offset&topic)
/memory/episodic/{userId}/search   POST
/memory/episodic/{userId}/{sessionId}  DELETE
```

No changes needed here.

---

## What Needs to Be Added

### 1. `POST /chat` — Core Chat Endpoint
**Priority: P0 — blocks all dev**

**Why:**
> From `08_context_assembly.md`: "Context is built from three layers before every LLM call."
> From `09_goal_anchoring.md`: "Repeat goal at bottom of context, right before user message."
> From `14_tech_stack.md`: "FastAPI handles all heavy lifting — LLM orchestration."
>
> The current Next.js route assembles context itself but it's wrong — it has no
> retrieval strategy, no prompt versioning, and no goal anchor. The frontend
> should never know *how* context is retrieved, only what it gets back.

**Request:**
```json
{
  "user_id": "demo_user",
  "topic": "AWS DVA-C02 — IAM",
  "mode": "planning" | "topic" | "doubt" | "evaluation",
  "tone": "tough" | "balanced" | "encouraging",
  "messages": [
    { "role": "user",      "content": "what are the things we are learning" },
    { "role": "assistant", "content": "..." }
  ]
}
```

**What the backend does internally (per `08_context_assembly.md`):**
1. Fetch in parallel: L1 (profile), L2 (skill node for topic + all skills by gap), L3 (last 3 sessions for topic via metadata filter)
2. Intent pre-check via Haiku: does this message need episodic context? If yes, run vector search too.
3. Load versioned prompt for `mode` from `prompts/session/{mode}.v1.md`
4. Assemble system prompt: prompt template + L1 (~200 tok) + L2 (~400 tok) + L3 if needed (~300 tok) + goal anchor (~50 tok)
5. Trim conversation history to last 6 turns (rolling window)
6. Call Claude Sonnet 4.6 (max_tokens 512)
7. Return response

**Response:**
```json
{ "text": "Here's the plan for AWS DVA-C02..." }
```

**Prompt files (already exist in repo — copy to backend):**
```
mentorman-app/prompts/session/planning.v1.md
mentorman-app/prompts/session/topic.v1.md
mentorman-app/prompts/session/doubt.v1.md
mentorman-app/prompts/session/evaluation.v1.md
```

**Special case — evaluation mode:**
> From `evaluation.v1.md`: The LLM emits two Claude tool calls:
> - `submit_verdict` (after each answer): `{ tone: Strong|Partial|Weak, feedback: string }`
> - `update_skill_graph` (after Q5): `{ new_level, weak_areas, strong_areas, eval_score }`
>
> When `update_skill_graph` fires, write it to MongoDB skill graph immediately (don't wait for session end).
> Return the text response to the frontend as normal; the tool-call side effect is invisible to the UI.

---

### 2. `POST /session/end` — Save Session with LLM Summary
**Priority: P1 — sessions save wrong without this**

**Why:**
> From `11_session_end_flow.md`: "One LLM call produces two outputs: narrative_summary
> (for Vector DB) and skill_update (structured JSON for MongoDB)."
> From `02_hybrid_storage.md`: "Two writes from one LLM call."
>
> The frontend currently does a manual raw-text POST to `/memory/episodic/{userId}` with
> no LLM processing and no skill graph update. This means the Vector DB gets garbage
> summaries and the skill graph never updates after sessions.

**Request:**
```json
{
  "user_id": "demo_user",
  "topic": "AWS DVA-C02 — IAM",
  "topic_category": "Cloud",
  "type": "Topic",
  "messages": [
    { "role": "user",      "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

**What the backend does:**
1. Call Claude Haiku with a summarizer prompt on the last 6 turns
2. LLM produces structured JSON:
   ```json
   {
     "title": "IAM roles vs users — when to use which",
     "narrative_summary": "3–5 sentences for semantic retrieval",
     "skill_update": {
       "current_level": "beginner",
       "weak_areas": ["IAM policy conditions"],
       "strong_areas": ["role vs user distinction"]
     }
   }
   ```
3. Write narrative_summary → embed (Voyage AI voyage-4-lite) + upsert to MongoDB sessions with metadata
4. Write skill_update → MongoDB upsert into skill_graph (merge, never overwrite missing fields)

**Response:**
```json
{
  "session_id": "uuid",
  "title": "IAM roles vs users — when to use which",
  "summary": "...",
  "skill_update": { ... }
}
```

**Migration:** Once this is live, replace the `fetch('/api/sessions', { method: 'POST', ... })` in
`mentorman-app/app/components/mentorman/chat.tsx:endSession` with a POST to `/session/end`.

---

### 3. `POST /onboarding/bootstrap` — Seed Skill Graph from Goal KB
**Priority: P1 — skill graph is empty without this**

**Why:**
> From `04_goal_knowledge_base.md`: "At onboarding, KB is queried for a match; if found,
> use curated entry; if not, LLM derives and creates it."
> From `10_onboarding.md`: "At end of onboarding, MongoDB writes Layer 2 (skill graph
> nodes with required_level from KB and gaps)."
> From `03_skill_graph.md`: "required_level comes from the Goal Knowledge Base — never
> guessed by the LLM."
>
> Right now the skill graph is empty after onboarding. All gap calculations and context
> assembly for L2 fail silently because there are no nodes.

**Request:**
```json
{ "user_id": "demo_user" }
```

**What the backend does:**
1. Read user's profile (goal)
2. Query Goal Knowledge Base for matching goal
3. If found: use curated required_levels per topic
4. If not found: call Claude Haiku to derive topic list + required_levels, store as `llm_derived`
5. Create skill graph nodes in MongoDB (one per topic) with `current_level = "beginner"`, gap calculated

**Response:**
```json
{ "ok": true, "topics_created": 8, "topics": ["IAM", "S3", "EC2", ...] }
```

**When called:** Immediately after profile creation succeeds in the onboarding flow
(`mentorman-app/app/components/mentorman/screens.tsx` → `Onboarding`).

---

## What the Next.js Route Becomes After Wiring

`mentorman-app/app/api/mentor/route.ts` shrinks to a thin proxy — remove the Anthropic SDK
import, `buildSystemPrompt()`, and all memory fetches:

```typescript
export async function POST(req: NextRequest) {
  const body = await req.json();
  const r = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: h(),
    body: JSON.stringify({ user_id: userId(), ...body }),
  });
  return NextResponse.json(await r.json(), { status: r.status });
}
```

`ANTHROPIC_API_KEY` moves out of `.env.local` entirely — it belongs only on the backend.

---

## Context Assembly Token Budget (from `08_context_assembly.md`)

```
System prompt (versioned, mode-specific)   ~100 tok
L1 Core Profile (always)                   ~200 tok
L2 Skill Graph nodes (topic + top gaps)    ~400 tok
L3 Episodic (conditional, if needed)       ~300 tok
Goal anchor reminder                       ~50  tok
Conversation history (last 6 turns)        ~500 tok
User message                               ~variable
─────────────────────────────────────────────────────
Total                                      ~1550 tok
```

L3 is conditional: run intent pre-check with Haiku first ("does this message reference
past sessions or need prior context?"). Skip L3 entirely for novel questions.

---

## Model Routing (from `14_tech_stack.md`)

| Call | Model |
|---|---|
| Main chat response | Claude Sonnet 4.6 |
| Intent pre-check (L3 needed?) | Claude Haiku 4.5 |
| Session title + summary | Claude Haiku 4.5 |
| Skill graph bootstrap (novel goal) | Claude Haiku 4.5 |
| Evaluation verdict parsing | Claude Sonnet 4.6 (already in main call) |

---

## Deferred to V2

- `POST /chat/stream` — SSE streaming (design is in `design docs/streaming-hld.md`)
- Ingestion pipeline (`/ingest/resume`, `/ingest/leetcode`) — `06_ingestion_pipeline.md`
- Alert cron + email notifications — `12_alerts_and_nudges.md`, `13_email_notifications.md`
- Drift detection (per-turn Haiku check) — `09_goal_anchoring.md`
- HybridAssembler / reranking — `design docs/context-assembler-hld.md`

---

## Auth

All requests: `X-API-Key: <MENTORMAN_API_KEY>` header (already enforced on memory endpoints).
