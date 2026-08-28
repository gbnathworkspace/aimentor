# Requirements Document

## Introduction

This document captures the requirements for a session-boundary-triggered narrative
summary, replacing the current message-count/token-threshold triggers as the source
of a topic's narrative memory. Today, a topic's only narrative summary comes from
`CompactionService` (see rolling-topic-summary spec), which fires when token usage
crosses a threshold (40%/60% of capacity) — and separately, `extract_skill_updates_only`
runs every `SKILL_CHECK_EVERY_N_MESSAGES` (16) messages but discards the `summary`
field it computes, applying only `skill_updates` and `taught_concepts`. Neither
trigger has any relationship to whether the student is actually still in one sitting:
a topic that goes idle for weeks and then gets a single follow-up question has that
follow-up folded into whatever message-count bucket it happens to land in, alongside
unrelated activity from a prior sitting.

This spec introduces a session concept scoped to a topic: a session is a run of
messages bounded by either a 10-minute inactivity gap or a logout. Each closed
session produces its own narrative-summary block. Because a long-lived topic can
accumulate many such blocks, blocks are progressively merged (oldest-pair-first)
whenever their combined word count exceeds a fixed budget, so storage stays bounded
without ever silently dropping a session's content below a minimum floor.

This spec does not change `CompactionService`'s token-threshold compaction of raw
messages, nor `taughtConcepts` — both continue to operate independently, per
Requirement 5.

## Glossary

- **Topic**: A persistent conversation thread with a title, belonging to a single
  user, that can span multiple visits over time
- **Session**: A run of consecutive messages within one topic, bounded by a 10-minute
  inactivity gap (from the previous message) or a logout event, whichever comes first
- **SummaryBlock** (this spec's usage): One narrative-summary entry covering one or
  more sessions, distinct from the RollingSummary of the rolling-topic-summary spec —
  see Requirement 4 for how the two coexist
- **Merge**: Combining the two oldest SummaryBlocks into one via a summarization LLM
  call, increasing that block's `mergeDepth` by one
- **Word Cap**: The maximum total word count across all of a topic's SummaryBlocks
  combined (default 500)
- **Word Floor**: The minimum word count a single SummaryBlock may be compressed to
  (default 50)
- **SessionManager**: Existing service (see `session_manager.py`) managing the
  separate, older `sessions_col` active/ending/ended state machine — not reused by
  this spec, which operates entirely on `topics_col` (see Requirement 6)

## Requirements

### Requirement 1: Session Boundary Detection

**User Story:** As a learner, I want my topic's narrative summary to reflect what
actually happened in one sitting, not an arbitrary slice of messages, so a summary
never blends unrelated activity from different days into one narrative.

#### Acceptance Criteria

1. WHEN a new message arrives for a topic AND the gap between its timestamp and the
   previous message's timestamp exceeds 10 minutes, THE System SHALL treat the run of
   messages since the last session close as a closed session and summarize it before
   appending the new message
2. THE System SHALL run a periodic sweep (default every 5 minutes) that finds topics
   whose most recent message is more than 10 minutes old and have not yet been closed
   through that message, and closes them the same way as Criterion 1 — covering the
   case where no next message ever arrives to trigger the lazy check
3. WHEN a user logs out, THE System SHALL immediately close the session for every
   topic that user has open, using their most recent message's timestamp as the
   close point, without waiting for the 10-minute gap
4. THE System SHALL measure the inactivity gap between two consecutive messages
   regardless of role (user or assistant) — i.e., the gap is wall-clock time since
   the last message in the array, not specifically since the last user message
5. IF a session-close is triggered (by gap, sweep, or logout) but no messages exist
   since the last close point, THEN THE System SHALL skip summarization for that
   close (no-op)

### Requirement 2: Per-Session Summary Block Creation

**User Story:** As a learner, I want each sitting I have with a topic to get its own
summary, so my most recent session is always represented in full detail rather than
compressed alongside older, unrelated activity.

#### Acceptance Criteria

1. WHEN a session closes, THE System SHALL generate a fresh, uncompressed narrative
   summary of that session's messages via the existing summarization LLM call
2. THE System SHALL create a new SummaryBlock with fields: `blockId`,
   `sourceSessionIds` (the closed session's message IDs), `text`, `wordCount`,
   `mergeDepth` (0 for a freshly created block), `createdAt` (the session's first
   message timestamp), and `lastMergedAt` (now)
3. THE System SHALL continue to extract `skill_updates` and `taught_concepts` from
   the same summarization LLM call and apply them exactly as `extract_skill_updates_only`
   does today, unaffected by this spec's changes to the `summary` field's handling
4. THE System SHALL NOT re-summarize messages already covered by an existing
   SummaryBlock's `sourceSessionIds` — a session-close only summarizes messages not
   yet covered by any block

### Requirement 3: Bounded Storage via Oldest-Pair Merging

**User Story:** As a system operator, I want a topic's total summary storage to stay
bounded regardless of how many sessions accumulate, without any single session's
content being silently deleted.

#### Acceptance Criteria

1. AFTER a new SummaryBlock is added (Requirement 2), IF the sum of `wordCount`
   across all of the topic's SummaryBlocks exceeds the Word Cap (default 500), THEN
   THE System SHALL merge the two oldest SummaryBlocks (by `createdAt`) into one new
   block via a summarization LLM call
2. THE System SHALL repeat the merge in Criterion 1 until the total word count is at
   or under the Word Cap, or until fewer than two blocks remain, or until 3 merge
   attempts have been made for this session-close (whichever comes first)
3. A merged block SHALL have `sourceSessionIds` equal to the union of the two merged
   blocks' `sourceSessionIds`, `mergeDepth` equal to one more than the greater of the
   two merged blocks' `mergeDepth`, and `createdAt` equal to the earlier of the two
   merged blocks' `createdAt`
4. THE System SHALL NOT compress any SummaryBlock's `wordCount` below the Word Floor
   (default 50) when merging — a merge that would otherwise reduce combined content
   below the floor SHALL still produce a block at least at the floor
5. IF the Word Cap cannot be reached after 3 merge attempts (Criterion 2), THEN THE
   System SHALL leave the topic's SummaryBlocks over-cap for this close, to be
   reduced further on the next session-close that adds a new block
6. WHEN merging leaves an odd number of blocks after some pairs have been merged
   in one close, THE System SHALL leave the unpaired block untouched — it becomes
   eligible for merging on a subsequent close, without special-casing which specific
   block is left unpaired

### Requirement 4: Coexistence with Existing Compaction

**User Story:** As a system operator, I want this spec's session-level summaries and
the existing token-threshold RollingSummary to operate independently, so introducing
session boundaries doesn't regress the existing compaction behavior that keeps raw
message storage bounded.

#### Acceptance Criteria

1. THE System SHALL continue to run `CompactionService.should_compact` and
   `_execute_compaction`'s token-threshold-triggered RollingSummary merge exactly as
   specified in the rolling-topic-summary spec, unmodified by this spec
2. THE System SHALL store this spec's SummaryBlocks separately from the
   rolling-topic-summary spec's single RollingSummary entry (distinct field on the
   topic document, e.g. `topic.summaryBlocks` vs. the existing `type == "summary"`
   entry in `topic.messages`)
3. THE System SHALL retire the existing message-count-triggered `extract_skill_updates_only`
   call path (every `SKILL_CHECK_EVERY_N_MESSAGES` messages) in favor of this spec's
   session-close trigger for `skill_updates` and `taught_concepts` extraction, so
   these are extracted once per closed session rather than once per fixed message count
4. A single session that never goes idle for 10 minutes but crosses the compaction
   token threshold SHALL still receive a RollingSummary merge mid-session per
   Criterion 1, independent of whether or when it eventually closes as a session

### Requirement 5: taughtConcepts Remains Independent

**User Story:** As a system operator, I want the concept-grained `taughtConcepts`
list to keep serving as the complete-coverage memory layer, unaffected by session-
level narrative summarization introducing its own compression.

#### Acceptance Criteria

1. THE System SHALL continue to append to `topic.taughtConcepts` exactly as
   `_apply_taught_concepts` does today, now triggered from session-close instead of
   the message-count checkpoint, with no other behavior change
2. THE System SHALL NOT read from or merge `taughtConcepts` when constructing or
   compressing SummaryBlocks — the two memory structures remain independent

### Requirement 6: No Dependency on the Legacy Session State Machine

**User Story:** As a system operator, I want this spec's session concept to be
purely topic-scoped and independent of the older `sessions_col`/`SessionManager`
model, so this change doesn't require reviving or coupling to that legacy system.

#### Acceptance Criteria

1. THE System SHALL determine session boundaries entirely from `topic.messages`
   timestamps and the logout event (Requirement 1) — it SHALL NOT read from or write
   to `sessions_col`, `SessionManager`, or `SessionSaveHandler`
2. THE System SHALL scope "logout closes the session" (Requirement 1.3) per-user
   across every topic that user currently has an unclosed session in, not limited to
   a single "active" topic concept

### Requirement 7: Context Assembly Exemption from Truncation

**User Story:** As a learner, I want my topic's session summaries to be readable in
full by the mentor, not silently cut off mid-sentence.

#### Acceptance Criteria

1. THE ContextAssembler's `_format_episodes` SHALL NOT apply its existing 300-character
   truncation to a topic's own SummaryBlocks (this spec) — that truncation SHALL
   continue to apply only to cross-topic episodic entries from `_recent_episodes`
2. THE ContextAssembler SHALL present a topic's SummaryBlocks in `createdAt` order
   (oldest first) when injecting them into the assembled context
