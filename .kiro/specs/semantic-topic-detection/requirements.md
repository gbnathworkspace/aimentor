# Requirements Document

> **Status note (2026-08-23):** `unified-backend/app/services/topic_router.py`
> shipped as an interim implementation of this same problem — a Haiku
> forced-tool_use call (MATCH / AMBIGUOUS / NEW), including a 4-candidate
> AMBIGUOUS pick-list not covered by Requirement 4.3 below. It directly
> contradicts this doc's "Out of scope: An LLM tiebreak or LLM classification
> of any kind" decision. Kept deliberately: it works, it's tested
> (`tests/unit/test_topic_router.py`, `tests/evals/test_topic_router.py`), and
> replacing it wasn't asked for. This spec remains the intended embedding-based
> replacement — reconcile the two (migrate to embeddings, or update this doc to
> ratify the LLM approach and drop/relocate the AMBIGUOUS requirement) before
> starting implementation here.

## Introduction

The welcome screen lets a user type without picking a topic. When they send,
`detectTopic()` (`mentorman-web/src/lib/topics/detectTopic.ts`) guesses which
existing topic the message belongs to; a hit renders the "Sounds like X" routing
card in `WelcomeScreen.tsx`, and the user chooses to continue that thread, start
a new one, or pick a different topic. A miss opens a new topic silently.

Detection today is **word overlap between the message and the topic's
title + subject**, scored as `matched terms ÷ topic's total terms`, best score
wins. It runs entirely client-side over the `/api/topics` list.

That is literal matching, and it fails in both directions on real messages:

- **False negative.** "In a component-based UI library that uses a virtual DOM…
  how do you prevent unnecessary re-renders…" scores **0** against the topic
  `React` — the word "react" never appears.
- **False positive.** That same message matches `Aws step functions` at 0.33,
  because the message contains "functions" and that title has three terms. The
  card then offers a confidently wrong thread.

Both were reproduced against the real topic list, not hypothesised.

This feature replaces word overlap with semantic similarity: embed the message,
compare it against per-topic embeddings, and route on the result. The user-facing
flow (the routing card, the picker, the confirm-before-routing behaviour) does
not change — only the function that decides which topic to name.

## What exists today

Traced across every embedding read and write in the backend:

| Path | Location | Writes / reads | Shape |
|---|---|---|---|
| `embed_text(text)` | `services/embedder.py:18` | Voyage `voyage-3`, async, returns `[]` on failure | — |
| Ingestion chunks | `services/extraction.py:175` | **writes** `embeddings_col` | `{user_id, job_id, text, embedding, metadata:{filename, chunk_index, source:"ingestion"}}` |
| Session summaries | `services/embedding_service.py:240` | **writes** `embeddings_col` | `{vector, text, metadata:{user_id, session_id, topic, mode, ended_at}}` |
| Episode search | `routers/memory.py:42` | **reads** via `$vectorSearch` | index `session_embedding_index`, path `embedding`, on **`sessions_col()`** |
| Document context | `services/context_assembler.py:109` | **reads** `embeddings_col` | plain `.find()`, no vector search |
| Recent episodes | `services/context_assembler.py:118` | **reads** `sessions_col()` | recency only, vector search deliberately avoided |

**Nothing in this table embeds a topic.** The only summary-embedding writer is
`session_save_handler.py:266`, on the legacy session-end path.
`topic_chat_service.py` never calls it — consistent with the finding already
recorded in `.kiro/specs/topic-delete/requirements.md` that the topic chat path
writes no `session_id` anywhere.

## Blocking observations

**1. There are no topic embeddings to search.** This feature cannot start from
"query the vectors we already have" — it has to create the write path first.
Requirements 1 and 2 exist for that reason.

**2. Three inconsistent shapes share one collection.** `embeddings_col` holds
ingestion chunks under `embedding` with a top-level `user_id`, and session
summaries under `vector` with `metadata.user_id`. A new topic writer must pick
one and state which, or add a third variant to the pile.

**3. The one `$vectorSearch` in the codebase may not be backed by an index.**
`memory.py` queries `sessions_col()` on `session_embedding_index`, while the
summary writer targets `embeddings_col`. `context_assembler.py:118` documents
this in a code comment — *"avoids both the missing Atlas index and the
writer/reader collection mismatch (#5)"* — and routes around it with a recency
query. Any design that assumes Atlas Vector Search works must verify the index
exists on the target cluster first.

**4. Detection runs before a topic exists.** It fires on the welcome screen, in
the same interaction as the send. Whatever it costs is latency the user feels
between pressing Enter and seeing either the card or the chat.

## Open decisions to resolve in design

**A. How the candidate search runs.**

1. **In-process cosine** (recommended). `list_topics` returns at most 50 topics
   (`topics.py:106-114`). Loading ≤50 stored vectors and scoring them in Python
   is negligible work, needs no Atlas index, and sidesteps observation 3
   entirely. Same reasoning `context_assembler` already applied.
2. **Atlas `$vectorSearch`.** Scales past 50 and matches `memory.py`'s
   precedent — but requires confirming the index exists, and creating one keyed
   to topics.

**B. What text represents a topic.** The title alone is a weak vector — `React`
is one word, and that weakness is exactly what breaks the current matcher. Options:
title only, title + first user message, title + last N messages, or the topic's
compaction summary when one exists. Pick one and state the re-embed trigger it
implies.

**C. Re-embedding cadence.** Every message is the most accurate and the most
Voyage calls; on topic create only is the cheapest and goes stale as a thread
drifts. A middle option is re-embed on compaction, which already runs.

**D. The match threshold.** A similarity floor is required (Requirement 4) but
its value has to be measured against real topics, not assumed. Design states how
it was picked and where the constant lives.

## Requirements

### Requirement 1 — Topics carry an embedding

**User Story:** As the detection code, I need a stored vector per topic, so that
a message can be compared against what a topic is about rather than what it is
called.

#### Acceptance Criteria

1. WHEN a topic is created THEN the system SHALL generate and store an embedding
   for it, derived from the text chosen in decision B.
2. WHEN a topic's representative text changes per the cadence in decision C THEN
   the system SHALL update the stored embedding for that topic.
3. THE stored record SHALL be keyed by `topicId` and SHALL carry `user_id`, so a
   search can be scoped to one user without a second lookup.
4. THE stored record SHALL use one of the two shapes already present in
   `embeddings_col`, and the design SHALL name which and why — a third variant
   is not acceptable.
5. IF embedding generation fails THEN the system SHALL leave the topic fully
   usable and SHALL NOT block topic creation or message sending —
   `embed_text` already returns `[]` rather than raising (`embedder.py:38-43`).
6. WHEN a topic is deleted THEN its embedding record SHALL be removed with it,
   per the cascade rules in `.kiro/specs/topic-delete/requirements.md`.

### Requirement 2 — Existing topics are backfilled

**User Story:** As a user with 28 existing topics, I want detection to work
against the threads I already have, not just ones created after the update.

#### Acceptance Criteria

1. THE system SHALL provide a way to generate embeddings for topics that predate
   this feature, following the script convention in `unified-backend/scripts/`
   (`migrate_sessions_to_topics.py`).
2. THE backfill SHALL be re-runnable without duplicating records for topics that
   already have one.
3. THE backfill SHALL skip and log topics whose embedding call fails, and SHALL
   continue rather than aborting the run.
4. WHEN a topic has no embedding for any reason THEN detection SHALL treat it as
   a non-candidate and SHALL NOT error.

### Requirement 3 — Detection endpoint

**User Story:** As the welcome screen, I want one call that tells me which
existing topic a message sounds like, so the client doesn't need the embedding
key or the matching logic.

#### Acceptance Criteria

1. THE system SHALL expose an authenticated endpoint under `/api`, using
   `require_auth` and the router conventions in `topics.py`.
2. THE endpoint SHALL accept the message text and return either one matched
   topic or an explicit no-match.
3. WHEN a match is returned THEN it SHALL carry enough for the routing card to
   render without a second request: at minimum `topicId`, `title`, and
   `lastActiveAt` (the card shows "last active 1 day ago" today).
4. THE endpoint SHALL only consider topics owned by the authenticated user, and
   SHALL only consider topics with status `active` — archived topics are not
   offered as routing targets.
5. THE endpoint SHALL bound the message length it accepts, consistent with the
   50,000-character cap on `SendMessageRequest` (`topics.py:48`).
6. THE endpoint SHALL NOT create, modify, or send anything — it is read-only, and
   the routing decision stays with the user.

### Requirement 4 — Match quality

**User Story:** As a user, I want the card to appear only when the guess is
actually good, because a wrong suggestion is worse than no suggestion.

#### Acceptance Criteria

1. THE system SHALL apply a minimum similarity threshold, below which it returns
   no match rather than the best of a bad set.
2. WHEN no topic clears the threshold THEN the client SHALL proceed straight to
   creating a new topic, with no card shown — the behaviour a miss has today.
3. THE system SHALL return at most one match; the card presents a single named
   topic and multi-select is not part of this flow.
4. THE threshold SHALL be a named constant, not a literal inline, so it can be
   tuned without re-reading the matching logic.
5. THE design SHALL record the two cases from the Introduction as the minimum
   bar: the virtual-DOM message SHALL match `React`, and SHALL NOT match
   `Aws step functions`.

### Requirement 5 — Frontend integration

**User Story:** As a user, I want the routing card to behave exactly as it does
now, because the improvement is in the guess, not in the interaction.

#### Acceptance Criteria

1. WHEN the user submits with no topic explicitly picked THEN the client SHALL
   consult the detection endpoint before opening a new topic.
2. WHEN the user has explicitly picked a topic from the picker THEN the client
   SHALL NOT call detection at all — an explicit choice is not second-guessed,
   as in `WelcomeScreen.tsx` today.
3. WHEN a match is returned THEN the client SHALL render the existing routing
   card with its three actions unchanged: continue this chat, start a new topic
   instead, pick a different topic.
4. WHEN detection is in flight THEN the client SHALL indicate that work is
   happening and SHALL prevent a duplicate submission of the same message.
5. WHEN the user edits the message text after a card is shown THEN the card SHALL
   be dismissed, as it is today — the guess no longer describes what was typed.
6. THE client-side `detectTopic.ts` SHALL either be removed or be reduced to the
   offline fallback in Requirement 6 — the codebase SHALL NOT carry two active
   matchers with different answers.

### Requirement 6 — Degradation

**User Story:** As a user, I want to keep chatting when the embedding provider is
down, because topic detection is a convenience and sending a message is not.

#### Acceptance Criteria

1. IF the detection call fails, times out, or returns no match THEN the client
   SHALL fall back to creating a new topic from the message — never to a blocked
   or errored send.
2. THE system SHALL NOT surface an error dialog for a failed detection; a missing
   suggestion is a silent non-event to the user.
3. THE detection call SHALL have a bounded wait, so a slow provider delays the
   send by a known ceiling rather than indefinitely.
4. IF `VOYAGE_API_KEY` is unset THEN the endpoint SHALL return no-match cleanly
   rather than raising, consistent with `embed_text`'s existing behaviour.
5. THE design SHALL state whether the word-overlap matcher is retained as an
   offline fallback or dropped; if retained, Requirement 4's threshold applies to
   it too, so it can no longer return the `Aws step functions` false positive.

### Requirement 7 — Ownership and privacy

**User Story:** As a user, I don't want my message text or topic list compared
against anyone else's data.

#### Acceptance Criteria

1. THE similarity search SHALL be filtered to the authenticated user's own topics
   before scoring, not filtered after.
2. THE endpoint SHALL return an identical no-match for "no topics cleared the
   threshold" and "the referenced topic isn't yours", consistent with the
   enumeration-prevention rule applied across `topics.py` (Req 15.5).
3. THE system SHALL NOT log raw message text at INFO level or above; detection
   runs on every unpicked send and the log file is retained 30 days
   (`main.py:46-52`).

### Requirement 8 — Verification

**User Story:** As the developer, I want the matcher covered by tests, because
"it feels better" is not a signal I can regress against.

#### Acceptance Criteria

1. THE system SHALL have a test asserting the threshold behaviour: a message that
   clears it returns a match, one that doesn't returns no-match.
2. THE system SHALL have a test covering the two named cases in Requirement 4.5.
3. THE system SHALL have a test asserting that a user's detection never returns
   another user's topic.
4. THE system SHALL have a test asserting that an embedding failure yields
   no-match rather than a raised error.
5. Backend tests SHALL follow the existing layout under `unified-backend/tests/`;
   any retained frontend matcher keeps its `vitest` coverage
   (`detectTopic.test.ts`).

## Out of scope

- An LLM tiebreak or LLM classification of any kind. Considered and deferred: the
  card already asks the user to confirm, so a close call costs a click. Revisit
  only if measured top-2 similarities are consistently indistinguishable.
- Reranking, or returning multiple candidate topics.
- Changing the embedding provider, or the `voyage-3` model choice.
- Fixing the wider `embeddings_col` schema inconsistency (observation 2) or the
  `sessions` / `embeddings` writer-reader mismatch (observation 3). This spec
  must not make either worse, and must not depend on either being fixed.
- Creating or repairing Atlas vector search indexes, unless decision A picks
  option 2 — in which case the index becomes a design prerequisite.
- Detection anywhere other than the welcome screen. Mid-conversation "this looks
  like a different topic" suggestions are a separate feature.
- Auto-routing without confirmation. The user always chooses.
- Subject/group assignment. Detection names a topic, not a subject
  (`.kiro/specs/subject-hierarchy`).
