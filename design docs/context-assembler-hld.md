# Context Assembler — High-Level Design

> **Status:** Design / pre-implementation  
> **Scope:** Swappable retrieval and prompt injection for the LLM call  
> **Related:** `architecture.md` — Layer 2 (SessionService) and Layer 3 (Data Layer)

---

## Problem Statement

`SessionService` needs to assemble context before every LLM call — it collects the user's Core Profile, relevant Skill Graph nodes, episodic memories, and a versioned prompt, then passes them all to Claude.

The retrieval method for episodic memories will change over time. Today it's pure semantic search (Voyage AI embeddings + cosine similarity). In the future it may be hybrid (semantic + BM25), topic-filtered, reranked, or something else entirely.

If `SessionService` calls Voyage AI directly, every retrieval change is a service-layer rewrite. That's the wrong layer to touch for an infrastructure decision.

---

## Design Goal

`SessionService` should never know *how* context is retrieved — only *what it gets back.*

The retrieval strategy must be swappable via a config change, with zero modifications to `SessionService`, zero UI changes, and zero schema changes.

---

## Core Interface

```typescript
// src/lib/context-assembler/types.ts

interface ContextAssembler {
  assemble(input: SessionInput): Promise<AssembledContext>
}

type SessionInput = {
  userId: string
  sessionId: string
  currentTopic: string          // detected by SessionService before calling
  conversationWindow: Message[] // last N messages
}

type AssembledContext = {
  systemPrompt: string           // versioned prompt for current mode
  coreProfile: CoreProfile       // always injected, no retrieval
  skillGraphNodes: SkillGraphNode[] // relevant to currentTopic
  episodes: Episode[]            // retrieved episodic memories
  conversationWindow: Message[]  // passed through unchanged
}
```

`AssembledContext` is Zod-validated on the way out of every assembler. If an implementation returns a malformed object, it's caught before the LLM call — not after.

---

## Factory

```typescript
// src/lib/context-assembler/factory.ts

export function createAssembler(): ContextAssembler {
  switch (process.env.RETRIEVAL_METHOD) {
    case 'hybrid':         return new HybridAssembler()
    case 'topic-filtered': return new TopicFilteredAssembler()
    case 'recency':        return new RecencyAssembler()
    default:               return new SemanticAssembler()
  }
}
```

`SessionService` imports `createAssembler()` once at startup. It never imports a concrete assembler directly.

---

## Concrete Assemblers

### 1. `SemanticAssembler` ← **current default**

Pure vector search. Embed the user's message, fetch top-K episodes by cosine similarity from the Vector DB.

```
embed(userMessage) → queryVector
vectorDB.search(queryVector, topK=5) → episodes
assemble(coreProfile + skillGraph + episodes + prompt) → AssembledContext
```

**When to use:** Sufficient for most cases. Good when the user's message is descriptive enough to produce a meaningful embedding.

**Weakness:** Fails on short or vague messages ("ok", "go on") — the query vector has no signal. Falls back to returning the most recent episodes.

---

### 2. `HybridAssembler` ← **add when retrieval quality needs improvement**

Runs semantic search and BM25 keyword search in parallel, merges results, then passes them through a `Reranker`.

```
embed(userMessage) → queryVector
vectorDB.search(queryVector, topK=10) → semanticResults
bm25.search(userMessage, topK=10)    → keywordResults
merge(semanticResults, keywordResults) → candidatePool (deduplicated)
reranker.rerank(userMessage, candidatePool) → top-5 episodes
```

**When to use:** When users frequently use jargon or topic names that semantic search misses (e.g., "Dijkstra" → keyword match is stronger than embedding match).

**Dependency:** Requires a `Reranker` implementation (see below).

---

### 3. `TopicFilteredAssembler` ← **add when episodic store is large**

Filters the episodic store by the current topic tag *before* running semantic search. Reduces the search space and avoids surfacing irrelevant episodes.

```
vectorDB.filter({ topic: currentTopic }) → topicSubset
embed(userMessage) → queryVector
vectorDB.search(queryVector, topK=5, within=topicSubset) → episodes
```

**When to use:** When the episodic store grows large (100+ sessions) and semantic search starts surfacing off-topic memories. Topic tag is written by `IngestionService` at session-end.

**Risk:** If the topic tag is wrong (mis-detected mode), retrieval misses. Needs a fallback to full-corpus search.

---

### 4. `RecencyAssembler` ← **fallback for new users**

No embedding, no vector DB. Just returns the last N sessions chronologically. Zero retrieval infrastructure dependency.

```
db.sessions.findMany({ userId, orderBy: 'desc', take: 5 }) → episodes
```

**When to use:** New users (episodic store is empty or near-empty, semantic search returns noise). Also useful as a test double — no external calls needed.

---

## Sub-Interface 1: `EmbeddingProvider`

`SemanticAssembler` and `HybridAssembler` both need to embed text. They call an `EmbeddingProvider` — not Voyage AI directly.

```typescript
interface EmbeddingProvider {
  embed(text: string): Promise<number[]>
  dimensions: number
}

// Implementations:
class VoyageProvider implements EmbeddingProvider   // current · voyage-large-2
class OpenAIProvider implements EmbeddingProvider   // text-embedding-3-large
class CohereProvider implements EmbeddingProvider   // multilingual support
```

Switching embedding models = swap the provider in the assembler's constructor. The assembler code does not change.

**Important:** When switching embedding models, the Vector DB must be re-embedded. Existing vectors are incompatible across models. See [Migration Procedure](#migration-procedure) below.

---

## Sub-Interface 2: `Reranker`

Used by `HybridAssembler` to score and sort the merged candidate pool.

```typescript
interface Reranker {
  rerank(query: string, docs: Episode[]): Promise<Episode[]>
}

// Implementations:
class CohereReranker implements Reranker  // cross-encoder model · best quality
class ScoreReranker implements Reranker   // recency × similarity blend · no API call
class IdentityReranker implements Reranker // no-op · pass-through (for testing)
```

`ScoreReranker` is a good default before investing in a cross-encoder — it's deterministic, has no external dependency, and is easy to debug.

---

## Data Flow (per LLM call)

```
User message arrives
      ↓
SessionService.handleMessage(message)
      ↓
  detects currentTopic (quick classification call)
      ↓
  assembler.assemble({ userId, sessionId, currentTopic, conversationWindow })
      ↓
  [inside assembler]
    ├── CoreProfileRepo.get(userId)          ← always, no retrieval
    ├── SkillGraphRepo.getByTopic(topic)     ← structured query
    ├── EpisodicRetriever.retrieve(input)    ← retrieval strategy runs here
    └── PromptStore.get(mode, version)       ← versioned file read
      ↓
  returns AssembledContext (Zod-validated)
      ↓
SessionService builds final prompt string
      ↓
Claude API call
      ↓
SessionService parses response
  ├── extracts any skill graph updates → SkillGraphService
  ├── extracts nudge signals → NudgeService
  └── returns message to UI
```

---

## Changing the Retrieval Method — Step by Step

This is the procedure for switching from one assembler to another in production.

**Step 1 — Implement the new assembler**
Create a new class implementing `ContextAssembler`. Add it to the factory switch. Write unit tests against the interface (the test contract is `AssembledContext`, not the internal retrieval logic).

**Step 2 — Shadow mode**
Run the new assembler in parallel with the current one for 1–2 days. Log both outputs. Compare `episodes` returned — check for relevance drift, missing context, empty results. Do not change what gets sent to Claude yet.

**Step 3 — Canary**
Enable the new assembler for 5–10% of sessions via feature flag. Monitor:
- Episode retrieval latency (p50, p95)
- LLM response quality (proxy: session length, nudge rate)
- Error rate (Zod validation failures, empty context)

**Step 4 — Promote**
Flip `RETRIEVAL_METHOD` env var. No code deploy needed.

**Step 5 — Clean up**
After 1 week stable, remove the old assembler class and its tests.

---

## Migration Procedure (embedding model switch)

When switching `EmbeddingProvider` (e.g., Voyage → Cohere):

1. **Do not delete existing vectors.** Write new vectors to a shadow collection/namespace.
2. Re-embed all existing episodic memories in the background (batch job).
3. Once 100% re-embedded, switch the `EmbeddingProvider` in the assembler and point to the new namespace.
4. Verify retrieval quality in shadow mode (Step 2 above).
5. Promote. Delete old vectors after 1 week.

**Never mix vectors from different models in the same search.** Cosine similarity across different embedding spaces is meaningless.

---

## File Structure

```
src/
  lib/
    context-assembler/
      types.ts                    ← SessionInput, AssembledContext (Zod schemas here)
      factory.ts                  ← createAssembler()
      assemblers/
        semantic.assembler.ts
        hybrid.assembler.ts
        topic-filtered.assembler.ts
        recency.assembler.ts
      providers/
        embedding/
          voyage.provider.ts      ← current
          openai.provider.ts
          cohere.provider.ts
        reranker/
          cohere.reranker.ts
          score.reranker.ts
          identity.reranker.ts    ← test double
```

---

## What Does NOT Change When You Swap Assemblers

| Layer | Changes? |
|---|---|
| `SessionService` | ✗ Never |
| UI components | ✗ Never |
| Zod schemas (`AssembledContext`) | ✗ Never (it's the contract) |
| MongoDB schemas (CoreProfile, SkillGraph) | ✗ Never |
| Claude API call | ✗ Never |
| Prompt files | ✗ Never |
| `.env` `RETRIEVAL_METHOD` var | ✓ Yes — this is the only change |
| New assembler file | ✓ Yes — new file added, nothing modified |

---

## Open Questions

- [ ] What is the right `topK` for each assembler? Start with 5, measure context window usage.
- [ ] Should `AssembledContext` include a `retrievalMeta` field for logging (which assembler ran, latency, episode IDs)? Useful for debugging retrieval quality.
- [ ] Shadow mode logging — where do these go? Separate logging table in MongoDB or a dedicated observability service?
- [ ] Topic tag reliability — `TopicFilteredAssembler` depends on accurate topic tags written at session end. How do we handle mis-tagged sessions?
