# Implementation Plan: Topic-Based Conversations with Compaction

## Overview

Replace the standalone session model with persistent topic-based conversations. Implement TopicService, CompactionService, TokenCounter, and adapt SessionService and ContextAssembler to work within topic threads. The system auto-summarizes older messages when the conversation window approaches capacity, firing skill graph updates at each compaction point. Includes UI components (topic sidebar, summary block indicators) and a migration path from existing sessions.

## Tasks

- [x] 1. Set up data models, interfaces, and project structure
  - [x] 1.1 Create TypeScript interfaces and data models for topics
    - Create `Topic`, `Message`, `SummaryBlock`, `CompactionEvent`, `TopicListItem` interfaces matching the design document data models
    - Create Zod schemas for runtime validation of Topic, Message, and SummaryBlock
    - Define `CompactionResult`, `CompactionConfig` types
    - _Requirements: 1.4, 4.1, 7.4, 7.5, 13.1, 13.2_

  - [x] 1.2 Create MongoDB collection setup and indexes for topics
    - Create `topics` collection with indexes on `userId + status + lastActiveAt` (compound), `topicId` (unique)
    - Create `compaction_events` collection with indexes on `topicId + timestamp`, `eventId` (unique)
    - Add a `version` field to the Topic document for optimistic concurrency control
    - _Requirements: 13.4, 14.2, 14.5_

- [x] 2. Implement TokenCounter utility
  - [x] 2.1 Implement TokenCounter with tiktoken-based estimation
    - Create `TokenCounter` class with `countMessage()`, `countWindow()`, `getCapacity()`, and `getUsagePercent()` methods
    - Use tiktoken (or character-to-token ratio heuristic) for fast token estimation
    - Calculate available capacity by subtracting fixed overhead (system prompt + L1 + L2 + L3 + goal anchor) from configurable total budget (default 200,000 tokens)
    - Implement staleness detection: full recount if cached estimate is older than 10 messages
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 2.2 Write property test for token arithmetic (Property 6)
    - **Property 6: Token Arithmetic Correctness**
    - Generate random capacity and overhead values → verify available capacity = total - overhead, and usage % = current / available × 100
    - **Validates: Requirements 5.2, 5.3**

  - [ ]* 2.3 Write property test for compaction threshold triggering (Property 7)
    - **Property 7: Compaction Threshold Triggering**
    - Generate random token usage values and thresholds → verify shouldCompact returns true iff usage exceeds threshold (60% default) or on-load exceeds 40%
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 3. Implement TopicService CRUD operations
  - [x] 3.1 Implement TopicService create, get, list, and archive methods
    - Implement `createTopic(userId, title)` with title validation (1–100 chars after trim)
    - Implement `getTopic(topicId)` with userId ownership check
    - Implement `listTopics(userId)` returning active topics ordered by lastActiveAt descending, max 50, with projection (topicId, title, status, lastActiveAt, message preview)
    - Implement `archiveTopic(topicId)` enforcing only active → archived transition
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Implement TopicService message operations
    - Implement `appendMessage(topicId, message)` with chronological ordering enforcement
    - Validate message content ≤ 50,000 characters, reject if topic status ≠ "active"
    - Update `lastActiveAt` and recalculate `currentTokenEstimate` on every append
    - Implement `getMessages(topicId, options)` with pagination support
    - Implement optimistic concurrency using version field with retry logic (up to 3 retries)
    - _Requirements: 4.1, 4.2, 4.5, 4.6, 13.1, 13.4, 13.5, 10.4, 10.5_

  - [ ]* 3.3 Write property test for topic title validation (Property 1)
    - **Property 1: Topic Title Validation**
    - Generate random strings → verify acceptance iff trimmed length is between 1 and 100 characters inclusive
    - **Validates: Requirement 1.4**

  - [ ]* 3.4 Write property test for topic listing correctness (Property 2)
    - **Property 2: Topic Listing Correctness**
    - Generate random sets of topics with various statuses → verify listing contains only active topics in descending lastActiveAt order
    - **Validates: Requirements 2.1, 2.3, 3.3**

  - [ ]* 3.5 Write property test for archive data preservation (Property 3)
    - **Property 3: Archive Data Preservation**
    - Generate a topic with random messages and summary blocks → archive it → verify status is "archived" and all data remains unchanged
    - **Validates: Requirements 3.1, 3.4**

  - [ ]* 3.6 Write property test for chronological ordering invariant (Property 4)
    - **Property 4: Chronological Ordering Invariant**
    - Generate random sequences of append and compaction operations → verify messages array maintains strict chronological order
    - **Validates: Requirements 4.1, 7.5, 13.1, 13.2**

- [x] 4. Checkpoint - Ensure TopicService and TokenCounter tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement CompactionService
  - [x] 5.1 Implement compaction message selection logic
    - Implement `selectMessagesToCompact(messages)` selecting oldest non-summarized messages first
    - Never split user-assistant message pairs
    - Select messages until token total meets or exceeds target reclamation amount
    - Skip compaction if fewer than 2 complete pairs are available
    - _Requirements: 7.1, 7.2, 7.7_

  - [x] 5.2 Implement CompactionService.shouldCompact and compact orchestration
    - Implement `shouldCompact(topicId)` checking token usage against configurable threshold (default 60%, range 30–90%)
    - Implement pre-emptive compaction check on topic load (>40% capacity)
    - Implement guard against concurrent compaction (skip if already in progress)
    - Implement `compact(topicId)` orchestrating: message selection → LLM summarization call → SummaryBlock creation → message replacement → skill graph update → CompactionEvent logging
    - Ensure messages are only removed after SummaryBlock is successfully persisted
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.3, 7.4, 7.5, 7.6, 10.3_

  - [x] 5.3 Implement compaction error handling and retry logic
    - On LLM failure: preserve all messages, skip compaction, retry next threshold crossing
    - Track consecutive failures per topic; after 3 failures, notify user to consider starting a new topic
    - On skill graph update failure: preserve summary block, queue skill update for retry (max 3 attempts)
    - Log all failures for operator review
    - _Requirements: 10.1, 10.2, 8.4, 8.5_

  - [ ]* 5.4 Write property test for message pair integrity (Property 5)
    - **Property 5: Message Pair Integrity During Compaction Selection**
    - Generate random message arrays → verify selection always includes complete user-assistant pairs and picks oldest first
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 5.5 Write property test for message conservation (Property 8)
    - **Property 8: Message Conservation (No Loss)**
    - Generate a topic with multiple compaction events → verify union of all compactedMessageIds + remaining raw message IDs equals the full original set
    - **Validates: Requirement 13.3**

  - [ ]* 5.6 Write property test for compaction safety on failure (Property 9)
    - **Property 9: Compaction Safety on Failure**
    - Simulate failed compaction (mock LLM error) → verify messages array remains completely unchanged
    - **Validates: Requirements 10.1, 10.3**

  - [ ]* 5.7 Write property test for compaction reduces token count (Property 10)
    - **Property 10: Compaction Reduces Token Count**
    - Generate successful compaction scenarios → verify currentTokenEstimate after < before, and tokensReclaimed = before - after
    - **Validates: Requirement 7.6**

- [x] 6. Checkpoint - Ensure CompactionService tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Adapt SessionService and ContextAssembler
  - [x] 7.1 Adapt SessionService to operate within topic threads
    - Replace sessionId references with topicId
    - Implement `handleMessage(topicId, userId, message)` flow: append user message → get messages → assemble context → LLM call → append assistant message
    - Implement `postTurnHook(topicId)` calling CompactionService.shouldCompact and triggering async compaction if needed
    - Handle LLM timeout (30s) and failure: retain user message, return error
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 6.4, 14.1_

  - [x] 7.2 Adapt ContextAssembler to handle SummaryBlocks
    - Update input type to accept `(Message | SummaryBlock)[]` in the conversation window
    - Position SummaryBlocks chronologically by compactedRange.from timestamp
    - Count SummaryBlock tokenCount toward conversation window budget
    - Skip malformed SummaryBlocks (failed Zod validation) with a warning log
    - L1, L2, L3 injection logic remains unchanged
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 7.3 Implement skill graph update extraction from compaction LLM call
    - Design the summarization prompt to produce both narrative summary and structured skill updates
    - Use structured output parsing (Zod) to extract zero or more skill node updates
    - Pass extracted updates to SkillGraphService for validation and persistence
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 8. Implement API routes for topics
  - [x] 8.1 Create topic API routes
    - POST /api/topics → create topic (with auto-create from first message support)
    - GET /api/topics → list topics for authenticated user
    - GET /api/topic/:id → get single topic with ownership check
    - PATCH /api/topic/:id → rename topic
    - POST /api/topic/:id/archive → archive topic
    - POST /api/topic/:id/message → send message within topic (triggers SessionService.handleMessage)
    - All routes validate authenticated userId ownership; return 403 for unauthorized, 404 for not found (identical error responses to prevent enumeration)
    - _Requirements: 1.1, 1.2, 1.3, 2.4, 3.1, 3.3, 4.1, 15.1, 15.2, 15.3, 15.5_

  - [ ]* 8.2 Write property test for access control enforcement (Property 13)
    - **Property 13: Access Control Enforcement**
    - Generate random userId × topicId combinations → verify operations succeed only when userId matches topic owner
    - **Validates: Requirements 15.1, 15.2**

- [x] 9. Checkpoint - Ensure API route and integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement UI components
  - [x] 10.1 Implement Topic Sidebar component
    - Create sidebar component displaying active topics ordered by lastActiveAt descending
    - Display title (truncated 60 chars + ellipsis), relative timestamp, and message preview (truncated 80 chars)
    - Handle empty state with prompt to start a new conversation
    - Handle topic load failure with error message while retaining current view
    - Wire up topic selection to navigate to /topic/{id}
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 10.2 Implement Topic Creation UI
    - Add "New Topic" button triggering title input
    - Support auto-creation from first message (no explicit title required)
    - Support renaming existing topics
    - Show validation errors for invalid titles
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 10.3 Implement SummaryBlock indicator in chat UI
    - Render collapsed SummaryBlock with "earlier messages summarized" label and compacted message count
    - Display date range formatted as "MMM D – MMM D, YYYY" (or single date if same day)
    - Style with smaller font size and muted background, inline with conversation flow
    - Implement expand/collapse toggle to reveal/hide full narrative summary
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 10.4 Implement archived topics view
    - Add archived topics listing accessible from sidebar
    - Display archived topics with title and last activity timestamp, ordered by lastActiveAt descending
    - Allow viewing archived topic content (read-only)
    - _Requirements: 3.4_

- [x] 11. Implement session migration
  - [x] 11.1 Create migration script for existing sessions to topics
    - Convert each existing session into a topic: use session title if present, otherwise derive from mode + topic field
    - Preserve all messages, timestamps, and ordering; set userId from session's user_id
    - Set status to "active", lastActiveAt to session's last message timestamp
    - Use original session_id as stable lookup key for idempotency (skip already-migrated sessions)
    - Skip sessions with zero messages
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 11.2 Write property test for migration data preservation (Property 11)
    - **Property 11: Migration Data Preservation**
    - Generate random sessions with messages → migrate → verify topic contains all messages in same order with same timestamps, status is "active", lastActiveAt equals last message timestamp
    - **Validates: Requirements 12.2, 12.3**

  - [ ]* 11.3 Write property test for migration idempotency (Property 12)
    - **Property 12: Migration Idempotency**
    - Generate random sessions → run migration multiple times → verify same set of topics produced, no duplicates
    - **Validates: Requirement 12.4**

- [x] 12. Implement performance optimizations
  - [x] 12.1 Implement async compaction and large topic handling
    - Ensure compaction runs asynchronously after response stream completes (non-blocking)
    - Implement lazy loading for topics with >500 messages: move older summary blocks to separate collection, load on scroll
    - Implement sidebar projection query for fast listing (< 500ms target)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (fast-check library)
- Unit tests validate specific examples and edge cases
- The design uses TypeScript throughout — all implementations follow this stack
- Compaction is the most complex subsystem; tasks 5.x should be implemented carefully with thorough error handling
- The migration script (task 11.1) should be run once during deployment transition

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["3.6", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.4"] },
    { "id": 6, "tasks": ["5.3", "5.5", "5.6", "5.7"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 8, "tasks": ["8.1"] },
    { "id": 9, "tasks": ["8.2", "10.1", "10.2"] },
    { "id": 10, "tasks": ["10.3", "10.4"] },
    { "id": 11, "tasks": ["11.1"] },
    { "id": 12, "tasks": ["11.2", "11.3", "12.1"] }
  ]
}
```
