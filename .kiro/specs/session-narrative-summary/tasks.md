# Implementation Plan: Session Narrative Summary

## Overview

Replace the message-count-triggered `extract_skill_updates_only` checkpoint with a
session-boundary trigger (10-minute inactivity gap or logout). Each closed session
gets its own SummaryBlock; blocks merge oldest-pair-first when total word count
exceeds a cap, bounded by a floor and a max-attempts limit. Keeps
`CompactionService`'s existing token-threshold RollingSummary and `taughtConcepts`
entirely unmodified.

## Tasks

- [ ] 1. Add the SummaryBlock storage shape
  - [ ] 1.1 Add `summaryBlocks: list[SummaryBlock]` field to the topic document model
    - Fields: `blockId`, `sourceSessionIds`, `text`, `wordCount`, `mergeDepth`,
      `createdAt`, `lastMergedAt` — see design.md Component 3
    - Default to `[]` for existing topics (no migration needed — additive field)
    - _Requirements: 2.2_

  - [ ] 1.2 Write model/schema tests for the new field
    - Empty default, round-trip serialization
    - _Requirements: 2.2_

- [ ] 2. Implement session boundary detection
  - [ ] 2.1 Add `session_boundary.py` with `check_and_close_on_new_message`
    - Compares new message timestamp to the topic's last message timestamp
    - Gap > 10 minutes (role-agnostic, Requirement 1.4) → calls `close_session`
      (task 3.1) before the new message is appended
    - _Requirements: 1.1, 1.4_

  - [ ] 2.2 Wire `check_and_close_on_new_message` into `topic_chat_service.py`
    - Called at the start of message handling, before `append_message`
    - _Requirements: 1.1_

  - [ ] 2.3 Add `idle_sweep()` and a startup-registered background loop
    - Queries topics with `lastActiveAt` older than 10 minutes and not yet closed
      through that point; calls `close_session` for each
    - Runs every 5 minutes via an `asyncio` background task started at app boot
      (no new job-queue infra — see design.md Performance Considerations)
    - _Requirements: 1.2_

  - [ ] 2.4 Add `close_all_sessions_for_user(user_id)` and wire into logout
    - Finds every topic with an unclosed session for the user, closes each
    - Called from the logout handler in `auth/router.py`
    - _Requirements: 1.3, 6.2_

  - [ ] 2.5 Write unit tests for boundary detection
    - Gap under 10 min → no close; gap over → close triggered
    - Sweep finds and closes a stale topic with no next message
    - Logout closes multiple open topics for one user, not just one
    - Empty `session_messages` at close time → no-op (Requirement 1.5)
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [ ] 3. Implement session summarization
  - [ ] 3.1 Add `session_summarizer.py` with `close_session(topic_id, user_id, upto_timestamp)`
    - Determines `session_messages` as messages not yet covered by any existing
      block's `sourceSessionIds`, up to `upto_timestamp`
    - Calls the existing `_call_summarization_llm` (imported from
      `compaction_service.py`, unchanged) — reuse, do not duplicate
    - Applies `skill_updates`/`taught_concepts` via the existing
      `_apply_skill_updates`/`_apply_taught_concepts`, unchanged
    - Builds a fresh SummaryBlock (`mergeDepth=0`) and appends it
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.2 Retire the message-count checkpoint call site
    - Remove the `elif total_messages % SKILL_CHECK_EVERY_N_MESSAGES == 0` branch
      in `topic_chat_service.py::_post_turn_hook`
    - `extract_skill_updates_only` itself can remain in `compaction_service.py`
      (still may be useful standalone) but is no longer called from this path
    - _Requirements: 4.3_

  - [ ] 3.3 Write unit tests for `close_session`
    - Fresh block created with correct fields
    - Already-covered messages excluded from re-summarization
    - LLM failure → no block persisted, messages remain uncovered for next attempt
      (Error Scenario 1)
    - _Requirements: 2.1, 2.2, 2.4_

- [ ] 4. Implement bounded-storage merging
  - [ ] 4.1 Add `_call_merge_two_blocks_llm(text_a, text_b) -> str`
    - New prompt variant combining two already-summarized blocks, respecting
      `BLOCK_WORD_FLOOR`
    - _Requirements: 3.1, 3.4_

  - [ ] 4.2 Add `enforce_word_cap(blocks) -> list[dict]`
    - While `sum(wordCount) > 500`: merge two oldest blocks by `createdAt`
    - Stop at cap reached, fewer than 2 blocks remaining, or 3 attempts
      (`MAX_MERGE_PASSES_PER_CLOSE`), whichever first
    - Merged block: union `sourceSessionIds`, `mergeDepth = max(a,b) + 1`,
      `createdAt = min(a,b)`
    - Odd block left over after pairing → left untouched this pass
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

  - [ ] 4.3 Wire `enforce_word_cap` into `close_session` after appending the fresh block
    - _Requirements: 3.1_

  - [ ] 4.4 Write unit tests for `enforce_word_cap`
    - Under cap → no merge
    - Over cap → merges oldest pair(s) until under cap
    - Floor respected — merge never asks for less than `BLOCK_WORD_FLOOR`
      (Property 2)
    - Merge attempt cap enforced — stops after 3 even if still over (Property 3)
    - Odd count → one block left unpaired, no special-case crash
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 4.5 Write property test for no-double-summarization (Property 1)
    - Union of `sourceSessionIds` across all blocks never contains a duplicate
      message ID, before or after any sequence of merges
    - _Requirements: 2.4, 3.3_

- [ ] 5. Checkpoint - Ensure session_boundary + session_summarizer tests pass

- [ ] 6. Integrate with ContextAssembler
  - [ ] 6.1 Add `_format_summary_blocks` alongside `_format_episodes` in `prompt_store.py`
    - Joins `topic.summaryBlocks` in `createdAt` order, no 300-char truncation
    - _Requirements: 7.1, 7.2_

  - [ ] 6.2 Exempt topic's own SummaryBlocks from `_format_episodes`'s 300-char cap
    - Cross-topic `_recent_episodes` entries keep the existing truncation
    - _Requirements: 7.1_

  - [ ] 6.3 Write regression tests for context assembly
    - A 500-word SummaryBlock is not truncated when injected
    - Cross-topic episodes are still truncated at 300 chars as before
    - _Requirements: 7.1, 7.2_

- [ ] 7. Confirm independence from existing systems
  - [ ] 7.1 Verify `CompactionService`'s RollingSummary merge is untouched by this spec
    - Existing rolling-topic-summary test suite passes unmodified
    - _Requirements: 4.1, 4.4_

  - [ ] 7.2 Verify `taughtConcepts` behavior is unchanged apart from its new trigger
    - Same append/cap logic as `_apply_taught_concepts` today, just called from
      `close_session` instead of `extract_skill_updates_only`
    - _Requirements: 5.1, 5.2_

  - [ ] 7.3 Verify no reads/writes to `sessions_col`, `SessionManager`, or
    `SessionSaveHandler` were introduced
    - _Requirements: 6.1_

- [ ] 8. Final checkpoint - Ensure full backend test suite passes

## Notes

- No new external services; reuses the existing Anthropic client and
  `_call_summarization_llm` from `compaction_service.py`.
- The idle sweep runs as an in-process `asyncio` background task, consistent with
  this app's single-process deployment — revisit only if this app moves to a
  multi-instance deployment (would need a distributed lock or single-owner sweep).
- This spec does not change how `CompactionService`'s token-threshold RollingSummary
  works — that remains exactly as specified in the rolling-topic-summary spec.

## Open Items Deferred (not blocking, noted for future work)

- No minimum-messages-per-session floor exists yet — a topic with many short bursts
  separated by >10min gaps could trigger frequent LLM calls. Not addressed in this
  spec; revisit if cost/frequency becomes a real issue.
- If `MAX_MERGE_PASSES_PER_CLOSE` is insufficient for a topic that grows very large
  very fast, blocks stay over-cap until the next close — accepted per Requirement 3.5.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1"] },
    { "id": 3, "tasks": ["2.5", "3.2", "4.2"] },
    { "id": 4, "tasks": ["3.3", "4.3"] },
    { "id": 5, "tasks": ["4.4", "4.5"] },
    { "id": 6, "tasks": ["5"] },
    { "id": 7, "tasks": ["6.1"] },
    { "id": 8, "tasks": ["6.2"] },
    { "id": 9, "tasks": ["6.3", "7.1", "7.2", "7.3"] },
    { "id": 10, "tasks": ["8"] }
  ]
}
```
