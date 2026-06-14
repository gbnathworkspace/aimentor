# Implementation Plan: Session Persistence

## Overview

This plan implements the end-to-end session persistence pipeline across the unified-backend (Python/FastAPI) and mentorman-web (TypeScript/React). Tasks are structured to build from foundational data models through service-layer logic to client-side wiring, with each step building on the previous. The existing `session_end.py` service and `sessions.py` router are refactored and extended rather than replaced from scratch.

## Tasks

- [x] 1. Define data models and schemas
  - [x] 1.1 Create Pydantic models for SessionDocument, Message, SkillUpdate, and SessionEndResult
    - Add file `unified-backend/app/models/session.py`
    - Define `SessionStatus` enum (`active`, `ending`, `ended`)
    - Define `Message` model with `role`, `content` (max 50,000 chars), `timestamp` (ISO-8601)
    - Define `SkillUpdate` model matching the Zod schema: `topic`, `new_level` (enum), `gap` (0–100), `weak_areas` (max 10), `strong_areas` (max 10), `eval_score` (optional)
    - Define `SessionDocument` model with all fields from the design
    - Define `SessionEndResult` response model
    - _Requirements: 1.1, 2.2, 5.1, 5.2_

  - [x] 1.2 Create MongoDB index migration script for sessions collection
    - Add file `unified-backend/app/core/indexes.py`
    - Define compound index `{ user_id: 1, status: 1 }` for stale session cleanup
    - Define compound index `{ status: 1, updated_at: 1 }` for timeout sweep
    - Implement `ensure_indexes()` function called on app startup
    - _Requirements: 1.7, 1.8_

- [x] 2. Implement SessionManager service
  - [x] 2.1 Create SessionManager with lifecycle state machine
    - Add file `unified-backend/app/services/session_manager.py`
    - Implement `create_session(user_id, mode, topic)` — inserts document with `status=active`, empty messages, UUID v4 session_id, timestamps
    - Implement `transition_status(session_id, user_id, new_status)` — validates `active→ending` and `ending→ended` only, rejects all others with 409
    - Implement `cleanup_stale_sessions(user_id)` — force-ends all `active`/`ending` sessions for the user with failure_reason
    - Wire `create_session` to call `cleanup_stale_sessions` first
    - Validate that `user_id` is present; return error if missing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9_

  - [x]* 2.2 Write property tests for session state machine (Properties 1, 2, 3, 4)
    - Add file `unified-backend/tests/property/test_session_state_machine.py`
    - **Property 1: State Machine Transition Validity** — verify only `active→ending` and `ending→ended` succeed; all others rejected
    - **Property 2: Session Creation Produces Valid Document** — verify all required fields present with correct types
    - **Property 3: Stale Session Cleanup on New Session Creation** — verify stale sessions ended before new one created
    - **Property 4: Failed End-Processing Still Completes Session** — verify session always reaches `ended` even on failure
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.5, 1.6, 1.8**

  - [x] 2.3 Implement 60-second timeout sweep for stuck `ending` sessions
    - Add a background task or startup hook in `session_manager.py`
    - Query sessions with `status=ending` and `updated_at` older than 60 seconds
    - Transition matching sessions to `ended` with `failure_reason="timeout"`
    - _Requirements: 1.7_

- [x] 3. Implement MessageStore service
  - [x] 3.1 Create MessageStore with atomic append and checkpoint operations
    - Add file `unified-backend/app/services/message_store.py`
    - Implement `append_messages(session_id, messages)` — uses `$push` with `$each`; rejects if session status ≠ `active` (returns 409)
    - Implement `checkpoint(session_id, messages)` — uses `$set` for full array replacement (idempotent)
    - Implement `get_messages(session_id)` — returns messages sorted by timestamp ascending
    - Include retry logic: 1 retry after 1s delay using idempotent write (match on session_id + message timestamp)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x]* 3.2 Write property tests for MessageStore (Properties 5, 6, 7, 8, 9)
    - Add file `unified-backend/tests/property/test_message_store.py`
    - **Property 5: Message Append Correctness** — verify array grows by 2, messages preserved at end
    - **Property 6: Message Chronological Ordering Invariant** — verify ordering after any sequence of operations
    - **Property 7: Idempotent Message Writes** — verify no duplicates on repeated writes
    - **Property 8: Message Persistence Rejects Non-Active Sessions** — verify 409 for ending/ended sessions
    - **Property 9: Orphaned Message Recovery Deduplication** — verify union with no duplicates after recovery
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.5**

- [x] 4. Implement SessionSaveHandler service
  - [x] 4.1 Create SessionSaveHandler with combined LLM call and response parsing
    - Add file `unified-backend/app/services/session_save_handler.py`
    - Implement `process_end(session_id, user_id, topic, mode)` orchestration method
    - Build combined LLM prompt requesting JSON with `narrative_summary` and `skill_update` keys
    - Include session topic and mode in the prompt for contextual summaries
    - Truncate transcript to most recent 40,000 characters if longer
    - Constrain LLM call to 500 output tokens, 30-second timeout per attempt
    - Implement retry logic: 3 total attempts with 2-second delay between retries
    - Parse response as JSON; on invalid JSON, attempt regex extraction for `narrative_summary`
    - Validate `skill_update` against Pydantic SkillUpdate model (equivalent to Zod)
    - On valid summary + invalid/missing skill_update: persist summary, skip skill graph
    - On valid skill_update + invalid/missing summary: update skill graph, use fallback summary
    - Generate fallback summary on total LLM failure: first + last user messages, max 300 chars, prefixed "Session covered:"
    - For sessions with <2 messages: use "Session ended before meaningful interaction occurred."
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.4, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x]* 4.2 Write property tests for SessionSaveHandler (Properties 10, 11, 13, 16, 17)
    - Add file `unified-backend/tests/property/test_session_save_handler.py`
    - **Property 10: Fallback Summary Generation** — verify correct fallback text construction and truncation
    - **Property 11: SkillUpdate Schema Validation** — verify accept/reject behavior against valid/invalid inputs
    - **Property 13: Invalid Skill Update Does Not Block Pipeline** — verify pipeline completes without skill update
    - **Property 16: LLM Response JSON Parsing** — verify independent extraction of both fields
    - **Property 17: Regex Fallback Extraction** — verify regex correctly extracts narrative from malformed JSON
    - **Validates: Requirements 4.4, 4.6, 5.2, 5.4, 7.2, 7.3, 7.4, 7.5**

  - [x] 4.3 Implement skill graph upsert via applyUpdate
    - Extend or reference existing `unified-backend/app/services/extraction.py` or create `unified-backend/app/services/skill_graph_repo.py`
    - Implement `applyUpdate(user_id, skill_update)` — upserts skill node with new_level, gap, weak_areas, strong_areas
    - Set `last_studied` to current ISO-8601 timestamp on every upsert
    - Log and skip on MongoDB write failure (non-blocking to pipeline)
    - _Requirements: 5.3, 5.6_

  - [x]* 4.4 Write property test for skill graph applyUpdate (Property 12)
    - Add file `unified-backend/tests/property/test_skill_graph_update.py`
    - **Property 12: Skill Graph applyUpdate Correctness** — verify node reflects update values and last_studied is recent
    - **Validates: Requirements 5.3, 5.6**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement EmbeddingService
  - [x] 6.1 Create EmbeddingService with async vector storage
    - Add file `unified-backend/app/services/embedding_service.py` (extends existing `embedder.py` patterns)
    - Implement `embed_and_store(summary, user_id, session_id, topic, mode, ended_at)`
    - Skip if summary is empty or <10 characters; log warning
    - Skip if any required metadata field is missing; log missing field names
    - Generate embedding via Voyage AI client
    - Upsert vector to Vector DB with metadata (user_id, session_id, topic, mode, ended_at)
    - Overwrite existing entry for same session_id (no duplicates)
    - Implement retry: 3 attempts, exponential backoff (1s, 2s, 4s, max 8s)
    - On total failure: log and enqueue for delayed retry (5 min)
    - Run asynchronously (fire-and-forget from session-end pipeline)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x]* 6.2 Write property tests for EmbeddingService (Properties 14, 15)
    - Add file `unified-backend/tests/property/test_embedding_service.py`
    - **Property 14: Embedding Storage Preconditions** — verify skip behavior for short summary or missing metadata
    - **Property 15: Embedding Idempotency** — verify exactly one entry per session_id after multiple calls
    - **Validates: Requirements 6.6, 6.7, 6.8**

- [x] 7. Wire API routes
  - [x] 7.1 Enhance existing sessions router with persistence endpoints
    - Modify `unified-backend/app/routers/sessions.py`
    - Enhance `POST /api/sessions` to use new SessionManager.create_session (returns session_id)
    - Add `POST /api/sessions/{id}/messages` — calls MessageStore.append_messages
    - Add `POST /api/sessions/{id}/checkpoint` — calls MessageStore.checkpoint
    - Enhance `PATCH /api/sessions/{id}` — on `status: ending`, trigger SessionSaveHandler.process_end, then transition to `ended`
    - Add `POST /api/sessions/{id}/recover` — calls SessionManager.recover_orphaned_messages
    - Add proper error responses (409 for invalid transitions, 400 for missing fields)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.9, 2.1, 2.5, 2.6, 3.5_

  - [x] 7.2 Integrate timeout sweep as a background task on app startup
    - Modify `unified-backend/app/main.py`
    - Register periodic background task (asyncio) to run timeout sweep every 30 seconds
    - Call `ensure_indexes()` on startup
    - _Requirements: 1.7_

  - [x]* 7.3 Write unit tests for API routes
    - Add file `unified-backend/tests/unit/test_session_routes.py`
    - Test session creation with valid/missing user_id
    - Test message append to active vs non-active sessions
    - Test status transition validation (valid and invalid)
    - Test session-end pipeline response structure
    - _Requirements: 1.1, 1.6, 1.9, 2.5, 2.6_

- [x] 8. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement client-side session persistence hook
  - [x] 9.1 Create `useSessionPersistence` React hook
    - Add file `mentorman-web/src/lib/session-persistence/useSessionPersistence.ts`
    - Implement `createSession(mode, topic)` — calls `POST /api/sessions`, stores session_id in state + localStorage, retry once after 2s on failure
    - Implement `persistMessages(userMsg, mentorMsg)` — calls `POST /api/sessions/{id}/messages`, retry once after 1s, queue to localStorage on failure
    - Implement `endSession()` — calls `PATCH /api/sessions/{id}` with `status: ending`, manages loading/disabled state, handles 30s timeout
    - Implement auto-checkpoint counter — triggers `POST /api/sessions/{id}/checkpoint` every 6 messages
    - Implement `beforeunload` handler — sends checkpoint on tab close, falls back to localStorage if request fails/times out (2s)
    - Implement `recoverOrphanedMessages()` — checks localStorage on mount, calls `POST /api/sessions/{id}/recover`, cleans up localStorage on success
    - Expose `sessionId`, `isEnding`, `error` state
    - Only clear localStorage drafts after 2xx response from backend
    - On session creation failure after retry: show error, disable input, show retry button
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x]* 9.2 Write tests for `useSessionPersistence` hook
    - Add file `mentorman-web/src/lib/session-persistence/__tests__/useSessionPersistence.test.ts`
    - **Property 18: Client localStorage Safety Invariant** — verify localStorage only cleared after 2xx
    - Test session creation flow with retry
    - Test message persistence with localStorage fallback
    - Test auto-checkpoint triggering at message count 6, 12, 18
    - Test beforeunload handler behavior
    - Test orphaned message recovery on mount
    - Test end session loading state and button disabling
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.7, 8.8, 8.9, 3.1, 3.3, 3.4**

- [x] 10. Wire hook into ChatPanel component
  - [x] 10.1 Integrate `useSessionPersistence` into existing ChatPanel
    - Modify the existing ChatPanel component to use the new hook
    - Call `createSession` on mount when no session_id exists
    - Call `persistMessages` after each mentor response stream completes
    - Call `endSession` on End Session button click
    - Call `recoverOrphanedMessages` on mount if localStorage has orphaned data
    - Disable message input and End Session button while `isEnding` is true
    - Display error states with retry button for session creation failures
    - Show loading indicator during session-end processing
    - Update sidebar with completed session title from `SessionEndResult`
    - Clear session_id from state and localStorage on successful end
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 8.6, 8.8, 8.9_

- [x] 11. Implement orphaned message recovery flow
  - [x] 11.1 Add recover endpoint logic and localStorage cleanup
    - In `SessionManager.recover_orphaned_messages`: deduplicate by (timestamp, role), append missing messages in chronological order
    - After recovery, trigger end-of-session processing for the recovered session (if not already ended)
    - Ensure recovery completes before new session's first LLM call
    - Client deletes localStorage entry only after successful recovery + end-processing confirmation
    - _Requirements: 3.5, 3.6, 3.7_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The existing `session_end.py` service is superseded by the new `SessionSaveHandler` — the old file can be deprecated once migration is verified
- The existing `sessions.py` router is enhanced in-place rather than replaced
- Backend uses Python (FastAPI + Pydantic), frontend uses TypeScript (React hooks + Vitest)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["4.4", "6.1"] },
    { "id": 6, "tasks": ["6.2", "7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2", "10.1"] },
    { "id": 10, "tasks": ["11.1"] }
  ]
}
```
