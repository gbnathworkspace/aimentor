# Requirements Document

## Introduction

`situations`/`contexts` on the L1 profile (`models/profile.py`, up to 20 entries
each) are flattened into one unlabeled string by
`prompt_store.py::_format_learning_context()` and injected into **every** mentor
message and every subtopic-generation call, with no topic-relevance filter.
`_format_learning_context(profile)` takes only the profile — it never sees
`body.topic` — so a situation irrelevant to the topic being discussed (e.g. "prepping
for a backend interview" while the topic is `React`) still gets injected and can
skew subtopic weighting.

This feature adds `classify_relevance`, a Haiku call that judges each situation/context
against a topic once, and an `l1_scope` field stored on the topic document that
consumers read instead of the raw lists. Full design narrative lives in the
[Topic Scoping Notion doc](https://app.notion.com/p/3be6ca71b05681858c50ea964e68310b);
this document exists to pin down the questions the Notion doc leaves open before
implementation starts.

## What exists today

Traced directly against this repo (`unified-backend/`):

| Path | Location | Behavior |
|---|---|---|
| `mentor_chat()` | `routers/mentor.py:45` | Calls `context_assembler.assemble(user_id, body.topic, last_user_message)` on **every** `POST /api/mentor` call. `body.topic` is a **string title**, not a `topicId`. |
| `context_assembler.assemble()` | `services/context_assembler.py:38` | Fetches `profile`, `skill` (by `{user_id, topic}` title match), episodes, documents. **Never fetches the topic document itself** — no `topics_col` read keyed by `topicId` exists on this path. |
| `_format_learning_context()` | `services/prompt_store.py:183` | Signature is `(profile: dict) -> str`. No `topic` parameter — matches the doc's own finding #5. |
| `TopicService.create_topic()` | `services/topic_service.py:35` | Takes `user_id, title` only. No relevance/classification step. Does **not** check title uniqueness per user. |
| `TopicService.get_topic()` | `services/topic_service.py:77` | Fetches by `{topicId, userId}` — this is the only clean "reopen" hook in the codebase today. |
| `situations` / `contexts` | `models/profile.py:23-33` | `max_length=20` each; no cap enforced at injection time. |
| Subtopic weighting | `services/subtopic_weights.py` | Already exists, unchanged by this feature per the Notion doc's "out of scope." |
| `langgraph` | `requirements.txt` | **Not present.** Only `langchain-anthropic>=1.5.5` is installed. The Notion doc's stack table assumes `langgraph` is available. |

## Blocking observations

**1. `mentor_chat` never resolves a topic document.** The whole `l1_scope`
consumption path (`prompt_store.py — _format_learning_context()`) assumes a
`topic.l1_scope` is readable "already fetched with the topic doc" (per the Notion
lifecycle diagram), but today `context_assembler.assemble()` takes a topic
**title string** and does not fetch `topics_col` by `topicId` at all. Wiring
`l1_scope` into the mentor-chat path is not a pure read — it requires a new lookup,
and `MentorRequest` needs to be checked for whether it already carries a `topicId`
this can key off of.

**2. Topic titles are not guaranteed unique per user.** `create_topic()` validates
length only. If `l1_scope`/`profileStamp` resolution in the mentor-chat path has
to go through title (because that's what `MentorRequest.topic` carries), two topics
named `"React"` would either collide or require disambiguation the current schema
doesn't support.

**3. `langgraph` is not an installed dependency.** The Stack table in the Notion
doc states it as confirmed, but it isn't in `requirements.txt` today. Needs to land
as part of this feature's dependency change, not assumed pre-existing.

**4. `classify_relevance`'s only stated input is a bare topic string.** The
sibling `semantic-topic-detection` spec (`.kiro/specs/semantic-topic-detection/requirements.md`,
decision B) independently flags that a bare topic title is a weak signal for
this kind of judgment (`"React"` is one word). The same weakness applies here:
judging relevance against just a title risks the same class of error this feature
is trying to fix.

## Decisions

Resolved in review (2026-08-16). Each replaces the corresponding open question
from the earlier draft of this doc.

**A. `l1_scope` lookup key — `topicId`.** `MentorRequest` gains a `topicId`
field; the frontend sends it and `mentor_chat()` resolves the topic document by
`{topicId, userId}`, the same key `get_topic()` already uses. No title-uniqueness
work required.

**B. Topic signal for `classify_relevance` — title + subject.** The call passes
the topic's title and its subject/category field (where one exists on the topic
doc) as the topic description, rather than title alone.

**C. `situations` and `contexts` — both judged, independently.** Every entry in
both lists gets its own `RelevanceJudgment` against the topic. No list is left
unfiltered.

**D. Failure fallback — fall back to unfiltered injection.** If `classify_relevance`
fails or times out during topic creation, `create_topic()` still succeeds with
`l1_scope` left unset; `_format_learning_context()` falls back to today's raw-flatten
behavior for that topic (Requirement 4.3 covers this — the failure path and the
"topic predates this feature" path are the same code path).

**E. Human review — none. Fully automatic.** `l1_scope` is computed and stored
directly at topic creation / reopen, with no interrupt or approval step (unlike
`SubtopicGeneratorAgent`'s `human_review` node, which is unrelated to this).

**F. `profileStamp` hash scope — `situations` + `contexts`.** The originally
discussed third field, `label`, was a legacy value with no dedicated field in the
current Memory settings UI (Context / Situation only) — the user couldn't see or
edit it directly, and it silently duplicated `situations[0]` in the injected
prompt. Rather than fold it into the stamp, `label` has been removed from
`LearningContextDetail` entirely (`models/profile.py`); every write path that used
to set `label` now writes directly into `situations`. `profileStamp` only ever
needs to cover `situations` + `contexts` as a result.

**G. Staleness trigger — `get_topic()` only.** `mentor_chat()` does not
perform a stamp-compare on every message; it trusts whatever `l1_scope` is
already stored on the topic document. This requires confirming (as a build-time
task, not a spec decision) that the frontend calls `get_topic()` on topic open,
before the first message of a session — otherwise a stale `l1_scope` can persist
for an entire session after a profile edit.

**H. `subtopic_generator.py` → `subtopic_weights.py` — ordering dependency.**
`subtopic_weights.py` SHALL NOT run against a topic's subtopics until a
`subtopic_generator.py` run for that topic has reached `finalize` (i.e.,
generated subtopics have been human-approved). This is a sequencing requirement
this feature introduces on top of the Notion doc's "separate, unchanged graph"
framing — the two graphs are code-independent but data-dependent.

**I. `SubtopicGenState` persistence — `topics_col`, as a field on the topic
document.** Reuses the existing collection and the `{topicId, userId}`
ownership/auth model `topic_service.py` already enforces between the `/start` and
`/resume` endpoints. No new collection.

**J. `RelevanceJudgment.reason` — discarded, not persisted.** Only `relevant:
true/false` is stored per entry in `l1_scope`; `reason` is used transiently
during the Haiku call for eval/debugging visibility at classification time but is
not written to the topic document.

## Requirements

### Requirement 1 — `classify_relevance` is callable and testable in isolation

**User Story:** As a developer, I want `classify_relevance` to be a pure function
with a stable contract, so it can be unit-tested against a labeled eval set
independent of topic-creation plumbing.

#### Acceptance Criteria

1. THE system SHALL expose `classify_relevance(topic: str, situations: list[str],
   contexts: list[str]) -> list[RelevanceJudgment]` as an importable function, not
   inlined into `TopicService.create_topic()`.
2. THE function SHALL return exactly one `RelevanceJudgment` per input situation/context,
   preserving input order.
3. IF the underlying Haiku call fails or times out THEN the function SHALL raise a
   typed exception rather than returning a partial or malformed list — the caller
   (Requirement 2) decides the fallback behavior per Open Question D.
4. THE system SHALL have an eval suite under `unified-backend/tests/evals/` with
   hand-labeled `(topic, situation, expected_relevant)` cases covering at minimum:
   the doc's own React/backend-interview failure case, an urgency/casualness
   confound pair, and one genuinely ambiguous case.

### Requirement 2 — `l1_scope` is computed and stored at topic creation

**User Story:** As the mentor-chat context assembler, I want a topic's relevant-only
situations already computed when the topic exists, so no per-message classification
call is needed.

#### Acceptance Criteria

1. WHEN `TopicService.create_topic()` runs THEN the system SHALL call
   `classify_relevance` with the user's current `situations`/`contexts` and store
   the result plus a `profileStamp` on the new topic document.
2. THE stored `profileStamp` SHALL be defined as a hash over a named, explicit set
   of profile fields (resolving Open Question F), not left implicit.
3. IF `classify_relevance` fails during topic creation THEN the system SHALL apply
   the fallback decided under Open Question D, and SHALL NOT leave `create_topic()`
   unable to complete.

### Requirement 3 — `l1_scope` is refreshed on topic reopen when stale

**User Story:** As a returning user who edited my profile, I want a topic I reopen
to reflect my current situations, not the ones from when I created the topic.

#### Acceptance Criteria

1. WHEN `TopicService.get_topic()` is called THEN the system SHALL compare the
   current profile's hash against the topic's stored `profileStamp`.
2. IF the stamps match THEN the system SHALL reuse the stored `l1_scope` without
   calling `classify_relevance`.
3. IF the stamps differ THEN the system SHALL re-run `classify_relevance` and
   overwrite both `l1_scope` and `profileStamp` on the topic document.
4. THE design SHALL state explicitly, resolving Open Question G, whether
   `mentor_chat()` also performs this check on every message or only relies on a
   prior `get_topic()` call — the two paths currently diverge in this codebase.

### Requirement 4 — Consumers read `l1_scope` instead of raw lists

**User Story:** As the prompt builder, I want to inject only topic-relevant
situations, so irrelevant ones stop bleeding into subtopic weighting and mentor
responses.

#### Acceptance Criteria

1. `_format_learning_context()` SHALL accept the topic's `l1_scope` (or the
   resolved topic document) as a parameter, in addition to or instead of the raw
   profile lists.
2. THE function SHALL format only entries marked `relevant: true` in `l1_scope`.
3. WHEN `l1_scope` is unset (e.g., a topic predating this feature, or a
   fallback path from Requirement 2.3) THEN the system SHALL fall back to today's
   unfiltered behavior rather than injecting nothing.
4. `mentor_chat()`'s call shape SHALL be updated only to the extent needed to pass
   a `topicId` (or resolve one) through to context assembly — resolving Open
   Question A is a prerequisite for this requirement.

### Requirement 5 — Backward compatibility for existing topics

**User Story:** As a user with topics created before this feature shipped, I want
my existing topics to keep working without a manual migration step blocking me.

#### Acceptance Criteria

1. THE system SHALL treat a topic document with no `l1_scope` field as
   equivalent to Requirement 4.3's fallback — not as an error state.
2. THE system SHALL NOT require a bulk backfill migration to ship this feature,
   consistent with the lifecycle's "computed on reopen" model — reopening any
   pre-existing topic SHALL trigger the same path as Requirement 3.

### Requirement 6 — Dependency and infra prerequisites

**User Story:** As the developer, I want the `langgraph`/`langchain` stack decided
in the Notion doc to actually be available before code that imports it is written.

#### Acceptance Criteria

1. THE system SHALL add `langgraph` to `requirements.txt` as part of this
   feature's changes (Observation 3).
2. THE design SHALL state where `SubtopicGenState` persists between the
   `/agents/subtopic-generator/start` and `/agents/subtopic-generator/resume`
   endpoints, resolving Open Question I.

## Out of scope

(Carried over from the Notion doc, unchanged)

- Subtopic weighting logic (`subtopic_weights.py`) — untouched by this feature.
- Weight × proficiency priority scoring — open question, not decided here.
- Deduplication of generated subtopics.
- A general-purpose L1 caching layer.
