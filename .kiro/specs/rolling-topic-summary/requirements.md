# Requirements Document

## Introduction

This document captures the requirements for replacing per-compaction SummaryBlock accumulation with a single rolling summary per topic. Today, `CompactionService` appends a new, independent SummaryBlock to a topic's `messages` array every time compaction fires, and `ContextAssembler` reads back only the most recent 3 via `_recent_topic_summaries(limit=3)`. This means storage grows unbounded (a long-lived topic can accumulate dozens of SummaryBlocks) while the LLM only ever sees the newest 3 — older summarized history becomes invisible to the mentor even though it is never deleted. This is the deferred half of issue #23 ("Bound conversation context").

This spec replaces that model: at each compaction, the existing rolling summary (if any) is merged with the newly-selected raw messages into one updated summary that replaces the previous one. A topic then has at most one summary block at any time, it is always current, and no read-time limit is needed.

## Glossary

- **Topic**: A persistent conversation thread with a title, belonging to a single user, that can span multiple visits over time
- **CompactionService**: The service that monitors token usage within a topic and orchestrates summarization when thresholds are crossed
- **RollingSummary**: The single SummaryBlock-equivalent structure per topic that is replaced (not appended to) at each compaction, produced by merging the prior RollingSummary with newly-compacted messages
- **ContextAssembler**: The service that assembles the full LLM context per call, reading from topic thread messages including the RollingSummary
- **SummaryBlock**: The pre-existing data structure (see topic-conversations-compaction spec) that this spec supersedes with RollingSummary semantics
- **Compaction_Threshold**: The configurable percentage of context window capacity (default 60%) at which compaction is triggered

## Requirements

### Requirement 1: Merge-on-Compact Summarization

**User Story:** As a learner, I want my topic's summarized history to stay condensed into one current summary so that returning to an old topic doesn't leave decades of disconnected summary fragments the mentor can't fully see.

#### Acceptance Criteria

1. WHEN compaction is triggered for a topic, THE CompactionService SHALL fetch the topic's existing RollingSummary (if one exists) in addition to selecting the oldest non-summarized messages for compaction
2. WHEN calling the summarization LLM, THE CompactionService SHALL pass both the existing RollingSummary's text (if present) and the newly-selected messages, and SHALL instruct the LLM to produce a single updated narrative summary that incorporates both
3. WHEN the merged summary is produced, THE CompactionService SHALL replace the topic's existing RollingSummary in place (same block position, same identifier) rather than inserting a second, independent block
4. IF a topic has no existing RollingSummary at compaction time, THEN THE CompactionService SHALL create the first RollingSummary from the newly-selected messages alone, positioned at the location of the first compacted message
5. THE CompactionService SHALL update the RollingSummary's `compactedRange.to` to the timestamp of the newest message included in this compaction, while preserving `compactedRange.from` from the original first compaction (i.e. the range only ever grows forward, never resets)
6. THE CompactionService SHALL update the RollingSummary's `tokenCount` and `compactedMessageIds` (union of prior and newly-compacted IDs) on every merge

### Requirement 2: Single-Block Invariant

**User Story:** As a system operator, I want each topic to hold at most one summary block so that storage stays bounded regardless of how long a topic stays active.

#### Acceptance Criteria

1. THE TopicService SHALL enforce that a topic's `messages` array contains at most one entry with `type == "summary"` at any time
2. WHEN a topic is migrated from the legacy multi-SummaryBlock model, THE System SHALL merge all existing SummaryBlocks (oldest to newest) plus their combined `compactedMessageIds` into a single RollingSummary via one summarization pass, run once per topic
3. IF the one-time migration's summarization LLM call fails for a topic, THEN THE System SHALL leave that topic's existing SummaryBlocks untouched and retry migration on the next compaction trigger for that topic
4. THE System SHALL NOT delete a topic's underlying raw messages that were already compacted into prior SummaryBlocks — only the SummaryBlock *entries* are consolidated, consistent with the existing "never lose messages" guarantee (Requirement 10.3 of topic-conversations-compaction)

### Requirement 3: Context Assembly Simplification

**User Story:** As a learner, I want the mentor to always see my topic's full summarized history, not just the most recent fragment of it, so responses stay grounded in everything I've studied in this topic.

#### Acceptance Criteria

1. WHEN assembling context for a topic, THE ContextAssembler SHALL include the topic's single RollingSummary (if present) without applying a fixed count limit across topic summaries
2. THE ContextAssembler SHALL remove the `limit=3` truncation currently applied by `_recent_topic_summaries`, since at most one RollingSummary can exist per topic under Requirement 2.1
3. THE ContextAssembler SHALL continue to combine the topic's RollingSummary with cross-topic L3 episodic results (`_recent_episodes`) using the existing same-topic-first ordering, applying any remaining token-budget limit only to the L3 episodic portion
4. IF the RollingSummary's token count alone would exceed the episodic portion of the context token budget, THEN THE ContextAssembler SHALL apply `token_budget.apply_token_budget_priority`-style truncation to the RollingSummary text rather than dropping it entirely

### Requirement 4: Error Handling for Merge Failures

**User Story:** As a system operator, I want a failed merge to never lose the previous summary so that a transient LLM error doesn't erase a topic's accumulated history.

#### Acceptance Criteria

1. IF the merge-summarization LLM call fails (timeout, error response, or malformed output), THEN THE CompactionService SHALL preserve the existing RollingSummary and the newly-selected raw messages unchanged, and SHALL retry on the next turn that crosses the Compaction_Threshold
2. THE CompactionService SHALL apply the same consecutive-failure counting and user notification behavior (3 consecutive failures → in-app notice) that exists today for standalone compaction failures
3. THE CompactionService SHALL never remove the newly-selected raw messages from the topic until the merged RollingSummary has been successfully persisted

### Requirement 5: Skill Graph Extraction Unaffected

**User Story:** As a learner, I want skill graph updates to keep firing at each compaction so that switching to rolling summaries doesn't regress learning-progress tracking.

#### Acceptance Criteria

1. THE CompactionService SHALL continue to extract skill graph updates from the same merge-summarization LLM call, unchanged from the existing per-compaction extraction behavior
2. THE CompactionService SHALL scope skill-update extraction to only the newly-selected messages in a given compaction pass, not the full merged summary text, to avoid re-deriving skill updates already applied from prior compactions
