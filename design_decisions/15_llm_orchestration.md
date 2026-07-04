# LLM Orchestration: Direct Anthropic SDK over LangChain

## Decision
All LLM calls go through the direct Anthropic SDK (`anthropic.AsyncAnthropic`).
No LangChain, no orchestration framework. FastAPI serves HTTP; the SDK talks
to Claude; everything in between is our own code.

Note: FastAPI and LangChain are not alternatives. FastAPI is the web
framework (routes, auth, streaming). LangChain is an LLM orchestration
library. Even with LangChain we would still need FastAPI. The real choice
was LangChain vs direct SDK for the orchestration layer — and the direct
SDK won.

## Why

### The orchestration is custom anyway
MentorMan's core is its own layered memory design — user profile (Layer 1),
skill graph (Layer 2), episodic memory with embeddings (Layer 3), plus
context assembly and goal anchoring. None of that maps onto LangChain's
memory classes (buffer, summary-buffer, etc.). Forcing it in means writing
the same custom code *plus* adapters to fit the framework's interface.

### The call patterns are simple
Every LLM call is single-shot: assemble context → one `messages.create` →
stream back. Sonnet for reasoning, Haiku for lightweight checks (intent,
titles, drift). No multi-step chains, no branching pipelines. A chain
framework would wrap one function call in layers of abstraction and remove
almost zero code.

### Vector search is one raw query
Atlas `$vectorSearch` with metadata filters runs as a single aggregation
pipeline. LangChain's MongoDB wrapper would hide the filter logic the
retrieval design depends on.

### Fewer layers to debug, visible cost
With the raw SDK we see exactly what prompt goes out and what streams back.
Anthropic usage is the only real variable cost — obscuring token flow
behind a framework works against cost control. LangChain is also a heavy,
fast-churning dependency with frequent breaking changes between versions.

## When to revisit

Adopt piecemeal, if at all — never rewrite the working core just to
"use LangChain."

```
Trigger                                     What to reach for
────────────────────────────────────────────────────────────────────────
Mentor turns become agentic                 LangGraph, or the Anthropic
(tool loops, branching, retries —           SDK's tool-use loop
watch for while-loops around
messages.create with growing state)

Need a second LLM provider                  LiteLLM (thinner than
(fallback, A/B cost testing)                LangChain for this)

Ingestion needs many formats fast           langchain-community document
(Notion, DOCX, HTML, transcripts)           loaders only — no chains

Serious prompt eval / tracing               Langfuse or Anthropic console
(evaluation loop grows up)                  before LangSmith
```

### What should NOT trigger it
More prompts, more call sites, longer conversations, compaction /
summarization — all still linear single-call plumbing the direct SDK
handles fine. The layered memory stays custom regardless: it is the
differentiating feature, and squeezing it into a framework's memory
interface would be a step backward.
