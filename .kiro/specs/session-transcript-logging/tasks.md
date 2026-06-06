# Implementation Plan: Session Transcript Logging

## Overview

This plan implements a non-blocking transcript logging sidecar that captures full Anthropic API request/response data for developer analysis. The implementation follows a bottom-up approach: data layer first (types, schemas, model, repository), then the core logger service, then integration into the existing API routes, and finally automated tests.

## Tasks

- [ ] 1. Define types and Zod schemas for transcript data
  - [ ] 1.1 Create TypeScript types and Zod schemas for transcript entries and documents
    - Create `lib/transcript/types.ts` with all TypeScript interfaces: `TranscriptEntry`, `TranscriptDocument`, `CaptureRequestParams`, `CaptureResponseParams`, `TranscriptMetadata`, `ProfileSnapshot`, `SessionType`, `UpsertEntryParams`, `ListParams`
    - Create `lib/transcript/transcript.schema.ts` with Zod schemas: `TranscriptEntrySchema`, `TranscriptDocumentSchema`, and validation helpers
    - Export both for use by model, repository, and logger
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 2.3, 3.1, 3.3, 3.5_

- [ ] 2. Create Mongoose model with TTL index
  - [ ] 2.1 Implement the Transcript Mongoose model
    - Create `lib/db/models/transcript.model.ts` following the existing pattern in `core-profile.model.ts` and `session.model.ts`
    - Define the schema with fields: sessionId (unique index), userId (index), sessionType, metadata (with sessionMode, topic, onboardingFieldsCollected, profileSnapshot), entries array
    - Add TTL index on `createdAt` field using a helper that parses `TRANSCRIPT_TTL_DAYS` (valid integer 1-365, default 30 days)
    - Log a warning if `TRANSCRIPT_TTL_DAYS` is invalid
    - _Requirements: 2.1, 2.2, 2.3, 4.7, 7.1, 7.2, 7.3_

- [ ] 3. Implement the Transcript Repository
  - [ ] 3.1 Create the TranscriptRepo data access layer
    - Create `lib/db/repositories/transcript.repo.ts` following the existing pattern in `session.repo.ts` and `core-profile.repo.ts`
    - Implement `upsertEntry()`: validate required fields (userId, sessionId, sessionType), use `findOneAndUpdate` with `$push` to append entries, `$setOnInsert` for initial fields, `upsert: true`
    - Implement `getBySessionId()`: return full transcript document or null
    - Implement `list()`: support optional filters (userId, sessionType, startDate, endDate), enforce limit (1-100, default 50), order by createdAt descending, return empty array when startDate > endDate
    - _Requirements: 2.4, 2.5, 2.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 3.2 Write property tests for TranscriptRepo
    - **Property 5: Document structure validation**
    - **Property 7: Append without duplication**
    - **Property 8: Validation rejection for missing fields**
    - **Property 11: Retrieval round-trip**
    - **Property 12: Filter correctness**
    - **Property 13: List ordering and limit enforcement**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 4.1, 4.3, 4.4, 4.5**

- [ ] 4. Checkpoint - Ensure data layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement the TranscriptLogger service
  - [ ] 5.1 Create the core TranscriptLogger service
    - Create `lib/transcript/transcript-logger.ts`
    - Implement `isEnabled()`: read `process.env.ENABLE_TRANSCRIPT_LOGGING` per-request, return true only for exact case-sensitive string `"true"`
    - Implement `captureRequest()`: generate UUID correlationId, record request timestamp (ISO-8601), store params in an in-memory map keyed by correlationId, return correlationId
    - Implement `captureResponse()`: record response timestamp, build full TranscriptEntry, trigger async persistence via the repository
    - Add backpressure: maintain a pending-operations counter, drop new entries (with console warning) when counter exceeds 50
    - Fire-and-forget persistence: do not await the write, increment/decrement counter, log errors to console with format `[TranscriptLogger] <error_type>: <message> | sessionId=<id>`
    - Log confirmation after successful persistence when enabled
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.2 Write property tests for TranscriptLogger
    - **Property 1: Request capture completeness**
    - **Property 2: Response capture with correlation**
    - **Property 3: Timestamp ordering invariant**
    - **Property 4: Error capture on failure**
    - **Property 14: Feature flag skip behavior**
    - **Property 15: Backpressure drop threshold**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 5.2, 6.4**

  - [ ]* 5.3 Write unit tests for TranscriptLogger
    - Test: Logger continues when persistence fails (Req 1.5, 6.2)
    - Test: Env flag checked per-request, not cached at startup (Req 5.3)
    - Test: Log confirmation produced after successful persistence (Req 5.4)
    - Test: Response returns before persistence completes (Req 6.1)
    - _Requirements: 1.5, 5.3, 5.4, 6.1, 6.2_

- [ ] 6. Checkpoint - Ensure logger service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Integrate TranscriptLogger into API routes
  - [ ] 7.1 Integrate logging into the mentor API route
    - Modify `app/api/mentor/route.ts`
    - Import TranscriptLogger, call `isEnabled()` at start of request
    - Before `client.messages.create()`: call `captureRequest()` with userId, sessionId, sessionType='mentor', routeIdentifier='mentor', system prompt, messages, model, maxTokens, and metadata (sessionMode, topic, profileSnapshot)
    - After response/error: call `captureResponse()` with correlationId and response/error data
    - Ensure no additional `await` on the logger — fire and forget
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.4, 3.5, 5.1, 6.1_

  - [ ] 7.2 Integrate logging into the onboarding chat API route
    - Modify `app/api/onboarding/chat/route.ts`
    - Import TranscriptLogger, call `isEnabled()` at start of request
    - Before `anthropic.messages.create()`: call `captureRequest()` with userId, sessionId, sessionType='onboarding', routeIdentifier='onboarding_chat', system prompt, messages, model, maxTokens, and metadata (onboardingFieldsCollected, profileSnapshot)
    - After response/error: call `captureResponse()` with correlationId and response/error data
    - Ensure no additional `await` on the logger — fire and forget
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.3, 3.4, 3.5, 5.1, 6.1_

  - [ ]* 7.3 Write unit tests for API route integration
    - Test mentor route: verify captureRequest called with correct params when enabled
    - Test onboarding route: verify captureRequest called with onboarding context
    - Test both routes: verify logger not called when feature flag disabled
    - Test both routes: verify response returned even if logger throws
    - _Requirements: 1.5, 5.1, 5.2, 6.1_

- [ ] 8. Add environment configuration
  - [ ] 8.1 Update environment configuration and documentation
    - Add `ENABLE_TRANSCRIPT_LOGGING` and `TRANSCRIPT_TTL_DAYS` to `.env.local.example` with comments
    - Add the variables to `.env` (set `ENABLE_TRANSCRIPT_LOGGING=true` for development)
    - _Requirements: 5.1, 7.1, 7.2_

- [ ] 9. Write property tests for TTL configuration parsing
  - [ ]* 9.1 Write property test for TTL parsing logic
    - **Property 16: TTL configuration parsing**
    - **Validates: Requirements 7.2, 7.3**

  - [ ]* 9.2 Write property tests for metadata and context capture
    - **Property 6: Chronological entry ordering**
    - **Property 9: Onboarding context capture**
    - **Property 10: Profile snapshot fidelity**
    - **Validates: Requirements 2.4, 3.3, 3.5**

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses `vitest` for testing and `fast-check` for property-based tests (both already installed)
- All file paths are relative to `mentorman-app/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1"] },
    { "id": 3, "tasks": ["3.2"] },
    { "id": 4, "tasks": ["5.1", "8.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "9.1", "9.2"] },
    { "id": 6, "tasks": ["7.1", "7.2"] },
    { "id": 7, "tasks": ["7.3"] }
  ]
}
```
