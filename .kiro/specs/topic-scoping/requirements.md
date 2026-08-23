# Requirements Document

## Introduction

Source: [Topic Scoping](https://app.notion.com/p/gbnathworkspace/Topic-Scoping-3be6ca71b05681858c50ea964e68310b)
(Notion, MentorMan > Flow > Topic).

L1 profile carries two free-text lists — `situations` and `contexts`
(`unified-backend/app/models/profile.py:22-33`, up to 20 entries each, 40
combined). `prompt_store.py::_format_learning_context()` flattens **all** of
them into `{{learning_context}}` on every mentor turn, by design — the
docstring states *"Nothing here is 'active' — whatever is in them is true of
them right now, so all of it is injected"* (`prompt_store.py:183-198`). There
is no per-topic filter: a situation about interview prep bleeds into a
completely unrelated topic like React, with nothing to separate topical
relevance from the situation's own urgency/casualness framing. This is the
one L1/L2/L3 layer in the context-assembly stack with no cap/rank/filter step
— conversation history is capped at 20 messages, L3 episodes at 3
(`context_assembler.py`); L1's lists are not.

This spec fixes that: a `classify_relevance` judgment, computed lazily and
cached on the topic document as `l1_scope`, filters `_format_learning_context`
to only the situations/contexts topically relevant to the topic being
discussed.

**Split from the source doc.** The Notion doc also proposes a new
`SubtopicGeneratorAgent` (LangGraph, human-review interrupt, two new
endpoints) that reuses `l1_scope` once computed. That agent is **out of
scope for this spec** — see [Out of scope](#out-of-scope) — and gets its own
requirements doc later. `l1_scope` filtering stands on its own value (fixes
the injection bug for every mentor turn today) and doesn't need the agent to
ship.

## Scope decisions

Resolved before writing acceptance criteria, since they contradict or
sharpen the source doc:

1. **Lazy, not creation-time.** The source doc's flowchart computes
   `l1_scope` inside `TopicService.create_topic()` and refreshes it on
   reopen if the profile changed. Decided instead: **no creation-time step**
   — `l1_scope` is computed (or refreshed) the first time it's *needed*,
   using the same stamp-based staleness check, uniformly on every path that
   reads a topic for use (`GET /topic/{id}`, and the pre-turn fetch inside
   `handle_message`). This collapses "create" and "reopen" into one code
   path instead of two, and a topic nobody ever revisits never pays for a
   Haiku call it doesn't need.
2. **No new dependency.** `classify_relevance` is one structured-output LLM
   call, not a multi-step graph — `langchain-anthropic` (already in
   `requirements.txt:19`) covers it. `langgraph` is only needed for the
   deferred `SubtopicGeneratorAgent` and is not added in this spec.
3. **Per-user by construction.** `l1_scope` lives on the `topics` document
   (`topics_col`, keyed by `topicId`/`userId`), not on any shared/global
   collection — no ambiguity here since this spec doesn't touch
   `subtopic_lists_col`.

## Requirements

### Requirement 1 — `classify_relevance` judgment

**User Story:** As the mentor prompt builder, I need a per-situation
relevance judgment against the current topic, so that only topically
relevant L1 context gets injected.

#### Acceptance Criteria

1. THE system SHALL implement an async `classify_relevance(topic: str,
   situations: list[str], contexts: list[str]) -> list[RelevanceJudgment]`
   function, where `RelevanceJudgment` has `situation: str`, `relevant:
   bool`, and `reason: str`.
2. THE function SHALL judge `situations` and `contexts` together in one call
   per topic (source doc: "a single shared Haiku call"), not one call per
   entry.
3. THE prompt SHALL instruct the model to judge topical connection only and
   explicitly ignore how urgent or casual the phrasing sounds — this is the
   load-bearing instruction that prevents the doc's documented failure case
   (`"casually looking for frontend"` vs. `"urgently need frontend"` must not
   flip `relevant` for the same topic).
4. THE function SHALL use `ChatAnthropic` with Pydantic structured output
   (`.with_structured_output()`), consistent with the rest of the codebase's
   LLM call pattern.
5. WHEN both `situations` and `contexts` are empty THEN the system SHALL
   return `[]` without making an LLM call — nothing to judge, no reason to
   pay for one.

### Requirement 2 — `l1_scope` storage on the topic document

**User Story:** As the context assembler, I want the relevance judgment
cached per topic, so that every mentor turn doesn't re-pay for a
classification call.

#### Acceptance Criteria

1. THE `topics` document schema SHALL gain two optional fields: `l1_scope`
   (the list of `RelevanceJudgment` results, or the relevant subset — exact
   shape decided in design.md) and `profileStamp` (a hash of the profile's
   `situations` + `contexts` at the moment `l1_scope` was computed).
2. Existing topic documents without these fields SHALL continue to load and
   function normally — no migration required, per Requirement 3's lazy
   compute.
3. THE fields SHALL be written via the existing `topics_col()` accessor and
   `TopicService`, consistent with how other topic-doc fields are read/written
   today (no new collection).

### Requirement 3 — Lazy, stamp-based (re)computation

**User Story:** As a user, I want stale relevance judgments corrected
automatically when I update my profile, without a background job scanning
every topic.

#### Acceptance Criteria

1. WHEN a topic is fetched for use (via `TopicService.get_topic()` — used by
   both `GET /topic/{topic_id}` and the pre-turn fetch in
   `topic_chat_service.py::handle_message` at line 198) AND `l1_scope` is
   absent OR `profileStamp` does not match a hash of the user's current
   `situations` + `contexts` THEN the system SHALL call `classify_relevance`
   and persist the refreshed `l1_scope` + `profileStamp` before returning.
2. WHEN the stored `profileStamp` matches the current profile hash THEN the
   system SHALL reuse the cached `l1_scope` and SHALL NOT call
   `classify_relevance`.
3. THE staleness check SHALL be a plain equality/hash comparison — no TTL,
   no scheduled job, no general-purpose cache-invalidation layer (source doc:
   "Explicitly out of scope").
4. IF `classify_relevance` fails (timeout, malformed output, API error) THEN
   `get_topic()` SHALL still return the topic (degrade to the pre-existing
   unfiltered behavior for that call — see Requirement 5) rather than
   failing the request.
5. Two concurrent recomputations for the same topic (e.g., a sidebar open
   racing a message send) MAY both run and the later write wins — no locking
   is required for this single-user-per-account app.

### Requirement 4 — Filtered injection into the mentor prompt

**User Story:** As the mentor, I want `{{learning_context}}` to contain only
what's relevant to the topic I'm actually discussing, so my responses (and
subtopic weighting) don't get skewed by an unrelated situation.

#### Acceptance Criteria

1. `prompt_store.py::_format_learning_context()` SHALL read from the
   current topic's `l1_scope` (relevant subset) instead of flattening the
   full raw `profile.learning_context_detail.situations` /
   `.contexts` lists.
2. THE call chain from `topic_chat_service.py::handle_message()` — which
   already fetches the `topic` document before calling
   `context_assembler.assemble()` — SHALL thread the topic's `l1_scope`
   through to the prompt-building step. (`context_assembler.assemble()`
   currently takes only a topic-title string, not the topic document or its
   `l1_scope` — the exact signature change is a design.md decision, not
   specified here.)
3. WHEN `l1_scope` has no relevant entries (all judged irrelevant, or the
   list is empty) THEN `_format_learning_context()` SHALL fall back to its
   existing `"Not specified"` output — it already does this for the
   no-context/no-situation case.
4. THE existing `label` field (predates `situations`, still written by
   onboarding/memory_editor) SHALL continue to be handled — decide in
   design.md whether `label` is judged for relevance like any other
   situation or always passed through.

### Requirement 5 — Failure handling

**User Story:** As a user, I don't want a classifier outage to break my
ability to chat.

#### Acceptance Criteria

1. IF `classify_relevance` fails during the lazy-compute step THEN the
   system SHALL log the failure with `user_id` + `topic_id` and proceed
   without a cached `l1_scope` for that call.
2. WHEN no usable `l1_scope` exists for a turn (never computed, or computation
   just failed) THEN `_format_learning_context()` SHALL fall back to
   today's behavior — inject the full unfiltered lists — rather than
   injecting nothing. Correctness over completeness was the tradeoff before
   this feature; a transient failure should not make it worse (silently
   dropping all L1 context).
3. A failed computation SHALL NOT be persisted as an empty `l1_scope` with a
   matching `profileStamp` — doing so would incorrectly look "fresh" and
   suppress retry on the next topic-open.

## Out of scope

- **`SubtopicGeneratorAgent`** — the LangGraph agent (`classify_relevance →
  generate_subtopics → human_review → finalize`), its two new endpoints
  (`POST /agents/subtopic-generator/start`, `.../resume`), and its
  `SubtopicGenState` — separate spec, reuses this spec's `classify_relevance`
  once both exist.
- Any change to `subtopic_lists_col` / `subtopic_weights.py` — unchanged,
  per the source doc.
- Weight × proficiency priority scoring — noted in the source doc as an open
  question, not decided there or here.
- Deduplication of situations/contexts — not attempted; `classify_relevance`
  judges the lists as given.
- A general-purpose L1 caching layer with TTL/invalidation — the
  stamp-based check on the topic document replaces this need.
- `langgraph` as a new dependency — not needed for a single structured-output
  call; deferred to the agent spec.
- Any UI surface for reviewing/editing `l1_scope` judgments — the source
  doc's UI mockup subpage was for the agent's human-review step, not this
  spec. `l1_scope` is an internal filtering mechanism with no user-facing
  affordance here.
- Evals (`classify_relevance_cases.yaml`, per-category accuracy bar) — the
  source doc has a full eval plan; whether that ships alongside this spec or
  as a fast-follow is a call for design.md, not repeated here as a hard
  requirement.
