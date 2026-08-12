# Implementation Plan: Rolling Topic Summary

## Overview

Replace `CompactionService`'s append-a-new-SummaryBlock behavior with merge-into-one-rolling-summary. Add a lazy migration path for topics that already carry multiple legacy SummaryBlocks, simplify `ContextAssembler._recent_topic_summaries` now that at most one block can exist, and keep the existing compaction trigger/threshold/error-handling logic untouched.

## Tasks

- [x] 1. Add the rolling-summary lookup helper
  - [x] 1.1 Implement `_find_rolling_summary(messages) -> dict | None` in `compaction_service.py`
    - Returns the single `type == "summary"` entry if exactly one exists
    - Returns the list of entries (for migration use) if more than one exists — used by task 3
    - Returns `None` if none exist
    - _Requirements: 2.1_

- [x] 2. Implement merge-on-compact summarization
  - [x] 2.1 Add `_call_merge_summarization_llm(existing_summary, selected_messages)` to `compaction_service.py`
    - When `existing_summary` is `None`: delegate to the existing `_call_summarization_llm(selected_messages)` unchanged
    - When present: prepend a synthetic `{"role": "PRIOR SUMMARY", "content": ...}` turn ahead of `selected_messages`, reusing the same prompt template (updated with fold-in instructions) and tool schema/parsing path
    - Reuse `_COMPACTION_TOOL_SCHEMA` and `_parse_tool_use_response` unchanged for output parsing
    - _Requirements: 1.1, 1.2_

  - [x] 2.2 Update `_execute_compaction` to replace instead of append
    - After message selection (existing Step 3, unchanged), call `_find_rolling_summary` on the topic's current messages
    - Call `_call_merge_summarization_llm(existing_summary, selected)`
    - Build the replacement RollingSummary: reuse `existing_summary["id"]` if present else new uuid; `compactedRange.from` = existing's `from` if present else `selected[0].timestamp`; `compactedRange.to` = `selected[-1].timestamp`; `compactedMessageIds` = union of existing's IDs and `selected` IDs; recount `tokenCount` from the merged summary text; set `updatedAt` to now
    - Build `new_messages`: remove the existing summary entry (if any) and the newly-selected raw messages, insert the one updated RollingSummary at the position of the first item removed in this pass
    - Persist via the existing optimistic-concurrency `update_one` call, unchanged
    - _Requirements: 1.3, 1.4, 1.5, 1.6_

  - [x] 2.3 Write unit tests for merge construction
    - No existing summary → behaves identically to current append (single block created)
    - Existing summary + new selection → resulting block has union'd `compactedMessageIds`, advanced `compactedRange.to`, unchanged `compactedRange.from`, and reused `id`
    - See `tests/unit/test_rolling_topic_summary.py::TestExecuteCompactionMerge`
    - _Requirements: 1.5, 1.6_

  - [ ]* 2.4 Write property test for compacted-ID conservation (Property 2)
    - Skipped for now — no `hypothesis`/property-testing library is set up in this Python codebase (the archived TS spec used `fast-check`, which doesn't apply here). `test_second_compaction_replaces_not_appends` covers the same invariant (union, no dupes) as a concrete example rather than a fuzzed property. Add `hypothesis` and a real property test if this logic gets more complex.
    - **Validates: Requirements 1.6, 2.4**

  - [ ]* 2.5 Write property test for range monotonicity (Property 3)
    - Skipped for the same reason as 2.4 — `test_second_compaction_replaces_not_appends` asserts `compactedRange.to` advances and `from` stays fixed for one merge; add a multi-iteration property test only if a bug surfaces here.
    - **Validates: Requirement 1.5**

- [x] 3. Implement lazy migration for legacy multi-block topics
  - [x] 3.1 Add `_migrate_legacy_summaries(topic_id, user_id, topic) -> dict | None` to `compaction_service.py`
    - Triggered from `_execute_compaction` before the normal merge flow when `_find_rolling_summary` finds more than one summary entry
    - Merges all existing SummaryBlocks oldest-to-newest via one summarization LLM call, unioning their `compactedMessageIds` and taking the earliest `from` / latest `to`
    - On LLM failure: leaves the topic's existing multiple SummaryBlocks untouched, returns `None`, and the normal compaction flow for this turn is skipped (retried next threshold crossing, consistent with existing failure handling)
    - _Requirements: 2.2, 2.3_

  - [x] 3.2 Wire migration into `_execute_compaction` ahead of the normal merge
    - If migration is needed and fails, do not proceed to the new-content merge this turn
    - If migration succeeds (or wasn't needed), the topic doc is refetched and compaction proceeds as normal in the same turn
    - _Requirements: 2.2, 2.3_

  - [x] 3.3 Write tests for migration + immediate compaction and migration failure
    - `test_merges_multiple_legacy_blocks_into_one`, `test_leaves_topic_untouched_on_llm_failure`, `test_compact_skips_this_turn_when_migration_fails` in `tests/unit/test_rolling_topic_summary.py`
    - _Requirements: 2.1, 2.2_

- [x] 4. Checkpoint - Ensure CompactionService merge and migration tests pass
  - All 9 new tests pass; full existing compaction suite (111 tests) still passes unchanged.

- [x] 5. Simplify ContextAssembler's topic-summary read path
  - [x] 5.1 Update `_recent_topic_summaries` in `context_assembler.py`
    - Dropped the `limit` parameter entirely — the query is now scoped to the current topic (`$match` on `title`) and returns 0 or 1 items, no truncation needed
    - _Requirements: 3.1, 3.2_

  - [x] 5.2 Verify `assemble()`'s combined episodes list still respects the overall L3 token/count budget
    - `episodes = (topic_summary + await _recent_episodes(...))[:3]` — topic-side `[:3]` hack removed, overall 3-slot cap on the combined list retained unchanged
    - _Requirements: 3.3_

  - [ ]* 5.3 Add truncation for an oversized RollingSummary (only if needed)
    - Not implemented — no evidence yet that a merged summary text grows large enough to matter (compaction's own prompt already caps summaries at 3-5 sentences). Add `token_budget`-style truncation here only if a real oversized-summary case shows up.
    - _Requirements: 3.4_

  - [x] 5.4 Write regression tests for the simplified read path
    - Updated `tests/unit/test_context_assembler.py::TestRecentTopicSummaries` for the new signature/semantics (topic-scoped, 0-or-1 result, no cross-topic fill); added empty-topic and no-summary-yet cases
    - _Requirements: 3.1_

- [x] 6. Checkpoint - Ensure ContextAssembler tests pass
  - Full `test_context_assembler.py` + `test_context_assembler_topics.py` suites pass (111 tests total across both compaction and context-assembler files).

- [x] 7. Confirm skill-graph extraction scope is unaffected
  - [x] 7.1 Verify `_call_merge_summarization_llm` extracts skill updates only from `selected` (newly-compacted) messages, not from the merged summary text
    - The merge call's tool-schema output (`skill_updates`) is derived from the LLM call, which is given `selected` as the content to analyze for progress — the prior summary is passed only as context, not as material to re-derive updates from
    - _Requirements: 5.1, 5.2_

  - [x] 7.2 Covered by existing skill-update tests
    - `test_compaction_orchestration.py::test_compact_with_skill_updates` and `test_compaction_event_logged_on_success` continue to pass unchanged against the new merge path, confirming extraction behavior is unaffected
    - _Requirements: 5.1, 5.2_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Full backend suite: 696 passed.

## Notes

- No new external services, no MongoDB schema migration (`updatedAt` is additive and optional).
- Migration is lazy/on-touch, not a batch backfill — appropriate for a single-user app with a small number of topics (ponytail: no cron/background job needed for this scale).
- Compaction trigger logic (`should_compact`, thresholds, `select_messages_to_compact`, concurrent-compaction guard, consecutive-failure notification) is entirely unchanged — this plan only touches what happens to the *output* of a compaction.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3"] },
    { "id": 6, "tasks": ["5.1"] },
    { "id": 7, "tasks": ["5.2", "7.1"] },
    { "id": 8, "tasks": ["5.3", "5.4", "7.2"] }
  ]
}
```
