# Research — Chat History & Knowledge Base (Memory) Analysis

Deep analysis of MentorMan's **chat-history** persistence and **knowledge-base / layered-memory** subsystems, benchmarked against 2026 agent-memory best practices (web + GitHub). Code-grounded; every claim cites the file it came from.

---

## Part 1 — Chat History

### How it works today
- **Storage:** each session is one document in the `sessions` collection with a `messages: [{role, content}]` array (`models/session.py`, `routers/sessions.py`).
- **Write path:** the chat client persists the running transcript via `PATCH /api/sessions/{id}` (`update_session`); `created_at/updated_at` maintained server-side.
- **Read path:** `GET /api/sessions/{id}` returns the full `messages` array; the client maps them back to bubbles (`chat.tsx`).
- **Crash recovery:** unsaved "new" sessions are mirrored to `localStorage` (`DRAFT_KEY`) on the client.
- **What the LLM actually receives:** the **frontend** accumulates the full message list and sends *all* of it to `/api/mentor` every turn (`chat.tsx` `send()`). The backend does **no** windowing or summarization of conversation turns.

### Findings
1. **Unbounded conversation context (HIGH).** The mentor call replays the entire transcript each turn. As a session grows this inflates latency, cost, and risks context-window overflow. The design docs (`08_context_assembly.md`) *specified* a "rolling window of last 6 turns + mid-session compression" — **not implemented**.
2. **Client-owned history (MED).** The window is assembled in the browser, so the policy can't be enforced or evolved server-side, and a malformed client could send anything.
3. **Token budgeting asymmetry (LOW).** We added a `tiktoken` token budget for *uploaded-file* immediate context, but **not** for *conversation turns* — the more likely overflow source.

### Best-practice benchmark
The standard ladder (LangChain/Mem0/LangMem, and the NirDiamant catalog) is: **buffer → sliding window → summary → summary-buffer → token-buffer**. The recommended production default is **ConversationSummaryBufferMemory**: keep the last *N* turns verbatim, summarize older turns, trigger summarization at ~70–80% of context capacity. MentorMan is at the lowest rung (full buffer), client-side.

---

## Part 2 — Knowledge Base / Layered Memory

### Intended design (ADR-001, context-assembler-HLD)
- **L1 Core Profile** (goal/deadline/level/availability) — always injected.
- **L2 Skill Graph** (per-topic levels/gaps) — always injected.
- **L3 Episodic Memory** — past session summaries, vector-retrieved *only when the message needs it* (an intent pre-check gates retrieval).

### How it works today
- **L1/L2:** `context_assembler.assemble()` loads `profiles` + `skill_graph`, builds the system prompt (`prompt_store`). ✓
- **L3 episodic:** on session end, `session_end.process_session_end()` asks Haiku (tool_use) for a `{title, narrative_summary, skill_update}`, embeds the narrative with **Voyage `voyage-3`** (`embedder.py`), and inserts a doc into the **`sessions`** collection with `embedding` + `type:"session"`. Retrieval is `$vectorSearch` over `sessions` (index `session_embedding_index`, pre-filtered by `user_id`/`topic`, `numCandidates = max(20, limit*10)`) in `context_assembler._vector_search` and `routers/memory.py`.
- **Document ingestion:** `/api/ingest` → `extraction.py` extracts PDF/CSV text, `chunk_text` (1000 chars, 200 overlap), embeds each chunk, and writes to the **`embeddings`** collection.
- **Immediate context:** chat-uploaded files land in `immediate_contexts` as raw text blocks and are injected verbatim into the mentor system prompt (now token-budget-trimmed).

### Findings
1. **🔴 Orphaned document knowledge base (CRITICAL).** `embeddings` is **written but never read** — `grep` shows the only reference outside its accessor is the *insert* in `extraction.py:175`. Nothing performs `$vectorSearch` over `embeddings`. **Users can ingest PDFs/CSVs, but that content is never retrieved into any answer.** The "knowledge base" RAG is effectively dead on the read side.
2. **🟠 Collection conflation (HIGH).** Live session transcripts *and* episodic summaries share the `sessions` collection, distinguished only by `type`/presence of `embedding`. `memory.list_episodes` returns both mixed; vector search runs over a collection that's mostly non-embedded live sessions. This muddies indexing, querying, and lifecycle.
3. **🟠 Vector index is out-of-band (HIGH).** `database.py._ensure_indexes` creates only B-tree indexes. `session_embedding_index` (and any `embeddings` index) must be created **manually in Atlas** — Atlas vector indexes can't be made via `create_index`. If it's missing, `$vectorSearch` throws and the code **silently returns `[]`** (graceful-degrade) → episodic memory is invisibly *off*. No startup check, no log-loud.
4. **🟡 Intent pre-check not implemented (MED).** The designed "does this need past context? yes/no" gate (saves a search + keeps context clean) is absent; vector search always runs.
5. **🟡 Three disconnected ingest/retrieve paths (MED).** Episodic (summaries, retrieved), document chunks (`embeddings`, orphaned), immediate context (raw inject, no RAG). No router decides which store answers a query (cf. "Memory Routing").
6. **🟡 Embedding drift (LOW).** Code uses `voyage-3`; `14_tech_stack.md` says `voyage-4-lite`. No embedding model/version/dimension stored alongside vectors → silent corpus mismatch if the model changes.
7. **🟡 numCandidates below guidance (LOW).** Best practice is `numCandidates ≥ 20× limit`; code uses `~10× limit`.
8. **No semantic/procedural memory.** Only episodic summaries exist. No extracted entity/preference facts (semantic) and no learned heuristics (procedural) — the two layers most associated with personalization gains in 2026 frameworks.

### Best-practice benchmark
- **Layered memory** is the 2026 standard: working (in-context), episodic (past interactions), semantic (facts/preferences), procedural (learned behavior). MentorMan has working (L1/L2) + episodic (L3); **missing semantic + procedural**.
- **Data layout (MongoDB RAG):** store chunks as separate documents (✓ `embeddings` does) so a hit identifies the *passage*, pre-filter before ANN (✓), and `numCandidates ≥ 20× limit` (✗, ~10×). Hybrid (vector + full-text) search recommended for recall (not used).
- **Frameworks:** Letta/MemGPT (self-editing tiered memory, pluggable **MongoDB** backend), Zep/Graphiti (temporal knowledge graph; tops LongMemEval), Mem0 (managed extraction). If memory becomes core, adopting one beats hand-rolling — Letta notably supports a MongoDB data layer.

---

## Prioritized recommendations

| # | Severity | Recommendation |
|---|---|---|
| 1 | 🔴 Critical | **Wire up document retrieval.** Add a `$vectorSearch` over `embeddings` and fold top chunks into `context_assembler` (a new "reference" layer, or merge into L3). Create its Atlas vector index. Without this, ingestion is pointless. |
| 2 | 🟠 High | **Server-side conversation memory.** Implement summary-buffer (keep last N turns verbatim, summarize older) in the backend; stop replaying the full client transcript. Reuse the existing `tiktoken` budget for the turn window. |
| 3 | 🟠 High | **Split collections.** `episodic_memory` (summaries+embeddings) vs `sessions` (live transcripts); give each its own indexes and lifecycle. |
| 4 | 🟠 High | **Make the vector index first-class.** Document/automate Atlas Search index creation; add a startup health check that logs loudly (or fails in prod) when `$vectorSearch` is unavailable, instead of silently returning `[]`. |
| 5 | 🟡 Med | **Add the intent pre-check** (Haiku yes/no) to gate L3 retrieval — as designed (latency + cleaner context). |
| 6 | 🟡 Med | **Memory routing** — one place that decides profile vs skills vs episodic vs documents per query. |
| 7 | 🟡 Low | Raise `numCandidates` to `≥ 20× limit`; store `embedding_model`+`dim` on each vector; reconcile `voyage-3` vs `voyage-4-lite`. |
| 8 | Future | Add **semantic memory** (entity/preference extraction) and consider **procedural memory**; evaluate adopting **Letta/Zep/Mem0** rather than expanding the hand-rolled layer. Measure with **LoCoMo / LongMemEval**. |

---

## Sources
- [Agent Memory at Scale 2026: Letta, Zep, Mem0, LangMem Compared](https://agentmarketcap.ai/blog/2026/04/10/agent-memory-vendor-landscape-2026-letta-zep-mem0-langmem)
- [Best AI Agent Memory Frameworks in 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)
- [Episodic Memory for AI Agents (Atlan)](https://atlan.com/know/episodic-memory-ai-agents/)
- [GitHub — NirDiamant/Agent_Memory_Techniques (30 techniques)](https://github.com/NirDiamant/Agent_Memory_Techniques)
- [MongoDB Docs — RAG with Atlas Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/rag/)
- [MongoDB Docs — Run Vector Search Queries ($vectorSearch, numCandidates)](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/)
- [Building a RAG Knowledge Base on MongoDB Atlas (DEV)](https://dev.to/mongodb/building-a-rag-knowledge-base-on-mongodb-atlas-4jmj)
- [Conversational Memory for LLMs (Pinecone/LangChain)](https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/)
- [LLM Chat History Summarization: Best Practices (Mem0, 2025)](https://mem0.ai/blog/llm-chat-history-summarization-guide-2025)
- [Context Window Management Strategies (APXML)](https://apxml.com/courses/langchain-production-llm/chapter-3-advanced-memory-management/context-window-management)
