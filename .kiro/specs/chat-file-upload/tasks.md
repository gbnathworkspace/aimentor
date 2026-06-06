# Implementation Plan: Chat File Upload

## Overview

This plan implements the chat file upload feature for MentorMan, enabling users to upload PDF and CSV files during live mentoring sessions. The implementation follows a bottom-up approach: utility functions first, then backend services, then context assembly integration, and finally the UI layer — ensuring each layer builds on verified foundations.

## Tasks

- [ ] 1. Implement utility functions and file validation logic
  - [ ] 1.1 Create file validation and formatting utilities
    - Create `mentorman-app/lib/chat-upload/utils.ts`
    - Implement `validateUploadFile(file: { name: string, size: number })` — accepts `.pdf`/`.csv` ≤ 10 MB, returns error message for invalid type or size
    - Implement `truncateFilename(name: string)` — returns original if ≤ 30 chars, first 27 + "..." if longer
    - Implement `formatFileSize(bytes: number)` — KB (no decimal) for < 1 MB, MB (1 decimal) for ≥ 1 MB
    - Implement `truncateMessage(message: string, limit?: number)` — truncates to 2000 chars by default
    - _Requirements: 1.3, 1.7, 1.8, 2.5_

  - [ ]* 1.2 Write property tests for file validation and formatting utilities
    - **Property 1: File validation accepts only valid type and size combinations**
    - **Property 2: Filename truncation preserves short names and truncates long ones**
    - **Property 3: File size formatting uses correct unit thresholds**
    - **Property 4: Accompanying message truncation at 2000 characters**
    - Create `mentorman-app/test/chat-upload/file-validation.property.test.ts`
    - Create `mentorman-app/test/chat-upload/message-truncation.property.test.ts`
    - **Validates: Requirements 1.3, 1.7, 1.8, 2.5**

- [ ] 2. Implement Session Upload Handler (backend API)
  - [ ] 2.1 Create the session upload API route
    - Create `mentorman-app/app/api/session/[sessionId]/upload/route.ts`
    - Implement `POST` handler with authentication via Clerk JWT
    - Validate session existence and ownership (403 if not found/not owned)
    - Validate session is active (400 if ended)
    - Check for concurrent uploads — reject with 409 if another job is `pending`/`processing` for this session
    - Delegate file type/size validation to existing `FileUploadHandler` (400 on failure)
    - Store file to S3, create `JobRecord` with `sessionId`, `uploadContext: "session"`, `accompanyingMessage` (truncated to 2000 chars, empty string if not provided)
    - Return 202 with `{ jobId }`
    - Enqueue file for asynchronous extraction
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 7.8_

  - [ ] 2.2 Create the job status API route
    - Create `mentorman-app/app/api/session/[sessionId]/upload/[jobId]/status/route.ts`
    - Implement `GET` handler returning `{ jobId, status, extractionReady, summary?, error? }`
    - Validate session ownership before returning status
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 2.3 Write unit tests for Session Upload Handler
    - Test auth validation (403)
    - Test inactive session rejection (400)
    - Test concurrent upload rejection (409)
    - Test file validation delegation (400 on invalid)
    - Test happy path (202 response with jobId)
    - Test `accompanyingMessage` truncation and empty string default
    - Create `mentorman-app/test/chat-upload/session-upload-handler.test.ts`
    - _Requirements: 2.1–2.8, 7.8_

  - [ ]* 2.4 Write property test for concurrent upload rejection
    - **Property 16: Concurrent upload rejection for active sessions**
    - Create `mentorman-app/test/chat-upload/lifecycle-guards.property.test.ts`
    - **Validates: Requirements 7.8**

- [ ] 3. Implement Session Context Injector
  - [ ] 3.1 Create the ImmediateContext MongoDB model and TTL index
    - Create `mentorman-app/lib/models/immediate-context.ts`
    - Define the `ImmediateContext` schema with fields: `sessionId`, `userId`, `jobId`, `filename`, `fileType`, `content`, `tokenCount`, `accompanyingMessage`, `active`, `createdAt`, `updatedAt`
    - Configure TTL index on `createdAt` (24 hours)
    - Add compound index `{ sessionId: 1, active: 1 }` and index on `{ jobId: 1 }`
    - _Requirements: 3.1, 3.4_

  - [ ] 3.2 Implement the Session Context Injector service
    - Create `mentorman-app/lib/ingestion/session-context-injector.ts`
    - Implement `createImmediateContext()`:
      - For PDF: tokenize extracted text with tiktoken (`cl100k_base`), truncate to 4000 tokens at sentence boundaries if exceeded
      - For CSV: generate human-readable summary listing each topic with easy/medium/hard/total counts
      - Store `ImmediateContext` document in MongoDB
      - Update `JobRecord` with `extractionReady: true`
      - Retry write once on failure; mark job `failed` if retry also fails
    - Implement `deactivateImmediateContext(jobId)`: set `active: false` when full ingestion completes
    - Ensure ImmediateContext is available within 5 seconds of extraction completion
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 3.3 Write property tests for token truncation and CSV summarization
    - **Property 6: Token truncation preserves sentence boundaries**
    - **Property 7: CSV summarization includes all topics with correct counts**
    - Create `mentorman-app/test/chat-upload/token-truncation.property.test.ts`
    - Create `mentorman-app/test/chat-upload/csv-summarization.property.test.ts`
    - **Validates: Requirements 3.5, 3.6**

  - [ ]* 3.4 Write property test for failed jobs never producing ImmediateContext
    - **Property 15: Failed jobs never produce ImmediateContext**
    - Add to `mentorman-app/test/chat-upload/lifecycle-guards.property.test.ts`
    - **Validates: Requirements 7.4**

- [ ] 4. Checkpoint - Ensure all backend services pass tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Extend Context Assembler for ImmediateContext integration
  - [ ] 5.1 Extend the Context Assembler to include ImmediateContext blocks
    - Modify existing assembler implementations in `mentorman-app/lib/context-assembler/assemblers/`
    - Query `ImmediateContext` collection for `{ sessionId, active: true }` on each LLM call
    - Insert ImmediateContext blocks between Skill Graph nodes and Episodic RAG results
    - Label each block with `[File: {filename}, uploaded {relative time}]`
    - Order multiple blocks by `createdAt` ascending (oldest first)
    - Include system instruction listing active uploaded files when any ImmediateContext is present
    - Remove system instruction when all ImmediateContext documents become inactive
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7_

  - [ ] 5.2 Implement token budget priority logic for ImmediateContext
    - When combined context exceeds token budget: drop ImmediateContext blocks oldest-first
    - Never drop Core Profile or Skill Graph nodes
    - Ensure final assembled context fits within configured token budget
    - Mark ImmediateContext as inactive when full ingestion completes (deduplication with Episodic RAG)
    - _Requirements: 4.4, 4.5_

  - [ ]* 5.3 Write property tests for context assembly
    - **Property 8: ImmediateContext assembly ordering and labeling**
    - **Property 9: Token budget priority drops ImmediateContext before core context**
    - **Property 10: ImmediateContext lifecycle governs system instruction inclusion**
    - Create `mentorman-app/test/chat-upload/context-assembly.property.test.ts`
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

- [ ] 6. Extend Ingestion Pipeline with session metadata
  - [ ] 6.1 Add session metadata fields to ingestion pipeline models
    - Extend `JobRecord` schema in `ingestion-pipeline/app/models/schemas.py` with `session_id`, `upload_context`, `accompanying_message` fields
    - Extend `ChunkMetadata` to include `upload_context` and `session_id` fields
    - Tag all artifacts (S3 path, JobRecord, chunks, embeddings) with `source_context: "session"` and `sessionId`
    - _Requirements: 2.7, 5.4_

  - [ ] 6.2 Implement structured merge logic for session uploads
    - Extend `StructuredParser` to handle session PDF uploads: overwrite Core Profile fields only where new extraction provides non-null values
    - Extend LeetCode aggregation: sum solved counts per topic per difficulty for existing topics, create new topic documents for new topics
    - _Requirements: 5.2, 5.3_

  - [ ] 6.3 Implement re-ingestion handling for session uploads
    - When same source category as prior onboarding upload: delete old onboarding chunks/facts, preserve all session-tagged data
    - When same source category as prior session upload: replace prior session-category data, preserve onboarding data and other-category session data
    - Process session uploads in FIFO order within the same job queue as onboarding uploads (no priority changes)
    - _Requirements: 5.5, 5.6, 5.7_

  - [ ] 6.4 Hook extraction completion into Session Context Injector
    - After extraction completes for session-uploaded files, call `SessionContextInjector.createImmediateContext()`
    - After full ingestion completes, call `SessionContextInjector.deactivateImmediateContext()`
    - _Requirements: 3.1, 3.2, 3.3, 4.5_

  - [ ]* 6.5 Write property tests for ingestion pipeline extensions
    - **Property 5: Session metadata tagging on all ingestion artifacts**
    - **Property 11: Structured facts merge overwrites only non-null new values**
    - **Property 12: LeetCode aggregates merge sums counts and creates new topics**
    - **Property 13: Re-ingestion data isolation by source context**
    - Create `mentorman-app/test/chat-upload/metadata-tagging.property.test.ts`
    - Create `mentorman-app/test/chat-upload/structured-merge.property.test.ts`
    - Create `mentorman-app/test/chat-upload/reingestion.property.test.ts`
    - **Validates: Requirements 2.7, 5.2, 5.3, 5.4, 5.6, 5.7**

- [ ] 7. Checkpoint - Ensure all backend and pipeline tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Chat Upload UI components
  - [ ] 8.1 Create the ChatUploadButton component
    - Create `mentorman-app/app/components/mentorman/chat/ChatUploadButton.tsx`
    - Render file attachment icon button in the chat input bar
    - Open native file picker filtered to `.pdf` and `.csv` on click
    - Client-side validation: reject unsupported types with inline error, reject files > 10 MB with inline error
    - Display preview chip with truncated filename (30 chars) and formatted file size
    - Allow removing selected file via dismiss control on the chip
    - Disable button while upload is in progress
    - Accept maximum 1 file per message
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.7, 1.8, 1.10, 1.11_

  - [ ] 8.2 Create the UploadMessage component
    - Create `mentorman-app/app/components/mentorman/chat/UploadMessage.tsx`
    - Render in conversation timeline showing filename, file type icon, and status badge
    - Status badge reflects processing state: uploading, pending, processing, ready, done, partial, failed, timeout, connection_lost
    - Display indeterminate progress indicator while uploading
    - Show extraction summary (max 80 chars) when status reaches "ready"
    - Show "Ingested" badge when job status reaches `done`
    - Show "Partial" badge with explanation when status is `partial`
    - Show "Failed" badge with error message from Job_Record when status is `failed`
    - Show "Timeout" badge with informational message when polling times out
    - Show "Connection Lost" badge with manual "Refresh Status" button on poll exhaustion
    - _Requirements: 1.5, 1.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8_

  - [ ] 8.3 Implement upload submission and polling logic
    - Wire ChatUploadButton into chat input submission flow (file + optional text message)
    - Upload file to `POST /api/session/{sessionId}/upload`
    - On 202 response, begin polling job status endpoint at 2-second intervals
    - Stop polling on terminal state (`done`, `partial`, `failed`) or 5-minute timeout (150 polls)
    - Retry failed poll requests up to 3 times at 4-second intervals before showing "Connection Lost"
    - Insert system message in conversation when status reaches "ready"
    - _Requirements: 1.4, 1.5, 1.12, 6.6, 6.7, 6.8, 6.9_

  - [ ] 8.4 Implement error handling and retry logic in UI
    - On network failure: show error on Upload_Message, enable Retry button
    - Retry button re-initiates upload without re-selecting file (max 3 retries)
    - After 3 retries exhausted: disable Retry button, re-enable attachment button, show "Upload could not be completed" message
    - On extraction failure: display failure reason from Job_Record, re-enable attachment button
    - _Requirements: 1.9, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 8.5 Write property test for extraction summary length
    - **Property 14: Extraction summary respects 80-character maximum**
    - Create `mentorman-app/test/chat-upload/summary-length.property.test.ts`
    - **Validates: Requirements 6.2**

  - [ ]* 8.6 Write unit tests for Chat Upload UI components
    - Test button rendering and disabled state
    - Test file picker filter for .pdf/.csv
    - Test preview chip display (truncated filename + formatted size)
    - Test file removal from preview
    - Test status badge transitions across all states
    - Test progress indicator display during upload
    - Test polling start/stop behavior
    - Test retry button interactions
    - Create `mentorman-app/test/chat-upload/upload-ui.test.tsx`
    - Create `mentorman-app/test/chat-upload/polling.test.ts`
    - _Requirements: 1.1–1.12, 6.1–6.9, 7.1–7.4_

- [ ] 9. Integration wiring and end-to-end verification
  - [ ] 9.1 Wire session upload flow end-to-end
    - Ensure ChatUploadButton → Session Upload Handler → Ingestion Pipeline → Session Context Injector → Context Assembler → LLM response references uploaded content
    - Verify non-blocking behavior: user can continue chatting while upload processes
    - Verify ingestion continues if session ends before completion
    - Ensure `ImmediateContext` TTL expiry falls back to conversation window gracefully
    - _Requirements: 7.5, 7.6, 7.7_

  - [ ]* 9.2 Write integration tests for upload flow
    - Test full upload → extraction → ImmediateContext creation flow
    - Test ImmediateContext inclusion in context assembly → LLM call
    - Test full pipeline completion → ImmediateContext deactivation
    - Test session end during processing (ingestion continues)
    - Test re-upload same category (prior data replaced)
    - Create `mentorman-app/test/chat-upload/integration/upload-flow.integration.test.ts`
    - Create `mentorman-app/test/chat-upload/integration/context-assembly.integration.test.ts`
    - _Requirements: 3.2, 4.1, 4.5, 5.6, 5.7, 7.5, 7.6, 7.7_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The ingestion pipeline extensions (Python) are in `ingestion-pipeline/` while the rest is TypeScript in `mentorman-app/`
- The existing `FileUploadHandler`, `ExtractorService`, `ChunkerService`, and `EmbedderService` are reused — no new extraction or embedding logic is needed
- `fast-check` is used for property-based tests, `vitest` for unit/integration tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "6.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.2", "6.2", "6.3"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.3", "3.4", "6.4"] },
    { "id": 3, "tasks": ["5.1", "6.5"] },
    { "id": 4, "tasks": ["5.2", "5.3"] },
    { "id": 5, "tasks": ["8.1", "8.5"] },
    { "id": 6, "tasks": ["8.2", "8.3"] },
    { "id": 7, "tasks": ["8.4", "8.6"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2"] }
  ]
}
```
