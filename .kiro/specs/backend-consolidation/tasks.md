# Implementation Plan: Backend Consolidation

## Overview

Consolidate all MentorMan backend logic into a single unified FastAPI application (`unified-backend`), replacing the existing scattered codebases (Next.js API routes, ingestion-pipeline, layered-memory-service). The implementation uses async Motor for MongoDB, pydantic-settings for configuration, and a router-per-domain organization.

## Tasks

- [x] 1. Set up project structure, configuration, and core infrastructure
  - [x] 1.1 Create the unified-backend directory structure and core files
    - Create the `unified-backend/` directory with `app/`, `app/config/`, `app/core/`, `app/routers/`, `app/services/`, `app/models/`, `app/prompts/`, and `tests/` subdirectories
    - Create `requirements.txt` with dependencies: fastapi, uvicorn, motor, pydantic-settings, anthropic, voyageai, python-multipart, boto3, pypdf, httpx
    - Create `.env.example` with all required environment variables
    - _Requirements: 1.1, 1.2, 13.1, 13.3_

  - [x] 1.2 Implement unified Settings class and database module
    - Create `app/config/settings.py` with pydantic-settings `Settings` class (MONGODB_URI, DATABASE_NAME, MENTORMAN_API_KEY, ANTHROPIC_API_KEY, VOYAGE_API_KEY, STORAGE_BACKEND, S3_BUCKET_NAME, S3_REGION, PORT, LOG_LEVEL)
    - Create `app/config/database.py` with async Motor client, `connect_db()`, `disconnect_db()`, `get_db()`, and collection accessor functions
    - Implement fail-fast validation for missing required env vars
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 1.3 Implement FastAPI app entry point with lifespan handler
    - Create `app/main.py` with lifespan context manager for DB connection lifecycle
    - Register health check endpoint at GET /health returning `{"status": "ok"}`
    - Wire up all routers (placeholder imports for now)
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 1.4 Implement auth middleware (security dependency)
    - Create `app/core/security.py` with `require_auth` dependency that validates X-User-Id and X-Api-Key headers
    - Return HTTP 401 for missing/invalid API key or missing user ID
    - Create `app/core/dependencies.py` for shared FastAPI dependencies
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 1.5 Write property test for auth enforcement (Property 1)
    - **Property 1: Auth Enforcement**
    - Generate random endpoints × header combinations → verify 401 for missing/invalid headers
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

- [x] 2. Checkpoint - Ensure infrastructure tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement data models and Profile CRUD
  - [x] 3.1 Create all Pydantic data models
    - Create `app/models/profile.py` with ProfileCreate, ProfileUpdate, ProfileResponse
    - Create `app/models/skill.py` with SkillNode, SkillUpdate
    - Create `app/models/session.py` with Message, SessionCreate, SessionDoc
    - Create `app/models/episodic.py` with EpisodicEntry, SearchQuery
    - Create `app/models/ingestion.py` with IngestionJobResponse
    - Create `app/models/chat.py` with MentorRequest, MentorResponse, OnboardingRequest, OnboardingResponse
    - _Requirements: 3.1, 3.5, 4.1, 4.4, 5.1, 5.2, 8.1, 11.5, 14.1, 14.2_

  - [x] 3.2 Implement Profile router (/api/profile)
    - Create `app/routers/profile.py` with GET, POST (201), PUT, DELETE endpoints
    - All endpoints use `require_auth` dependency to scope data access by user_id
    - Handle 404 when profile not found, 409 for duplicate creation
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 3.3 Write property test for profile round-trip (Property 3)
    - **Property 3: Profile Round-Trip**
    - Generate random valid profile data → verify POST then GET returns same values
    - **Validates: Requirements 3.3, 3.5, 10.1**

  - [ ]* 3.4 Write property test for user data isolation (Property 2)
    - **Property 2: User Data Isolation**
    - Generate random user pairs × CRUD operations → verify user_A cannot access user_B's resources
    - **Validates: Requirements 2.5, 5.4, 11.8**

- [x] 4. Implement Skills CRUD and Session Management
  - [x] 4.1 Implement Skills router (/api/skills)
    - Create `app/routers/skills.py` with GET (list all), GET /{topic}, POST (upsert, 201), PUT /{topic}, DELETE /{topic}
    - Handle 404 for missing topic, scope all queries by user_id
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 4.2 Write property test for skill graph round-trip (Property 4)
    - **Property 4: Skill Graph Round-Trip**
    - Generate random valid skill node data → verify upsert then GET returns matching values
    - **Validates: Requirements 4.4, 4.5, 6.3**

  - [ ]* 4.3 Write property test for dual level format acceptance (Property 11)
    - **Property 11: Dual Level Format Acceptance**
    - Generate all level strings (beginner, intermediate, advanced, expert) + numeric gaps → verify acceptance
    - **Validates: Requirements 14.4**

  - [x] 4.4 Implement Sessions router (/api/sessions)
    - Create `app/routers/sessions.py` with GET (list, ordered by creation desc), POST (create, 201), GET /{sessionId}, PATCH /{sessionId}
    - Enforce user ownership (403), handle 404 for missing sessions
    - Support optional limit parameter on list endpoint
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 4.5 Write property test for session ordering (Property 5)
    - **Property 5: Session Ordering Invariant**
    - Generate random session creation times → verify GET returns strictly non-increasing order
    - **Validates: Requirements 5.1**

- [x] 5. Checkpoint - Ensure CRUD tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement services layer (context assembler, embedder, session end)
  - [x] 6.1 Implement embedder service
    - Create `app/services/embedder.py` with `embed_text(text: str) -> list[float]` using Voyage AI async client
    - Handle API failures gracefully
    - _Requirements: 8.1, 6.2_

  - [x] 6.2 Implement context assembler service
    - Create `app/services/context_assembler.py` with `assemble(user_id, topic, query)` function
    - Fetch L1 profile, L2 skill node, and perform L3 vector search (top 3 episodes)
    - Implement graceful degradation: 400 if no profile, empty skill/episodes on failure
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 6.3 Implement prompt store service
    - Create `app/services/prompt_store.py` mapping modes (planning, topic, doubt, evaluation) to prompt templates
    - Create `app/prompts/mentor_v1.md` and `app/prompts/onboarding.md` prompt templates
    - _Requirements: 7.5_

  - [x] 6.4 Implement session end processor service
    - Create `app/services/session_end.py` with `process_session_end(user_id, topic, messages)` function
    - Call Anthropic for summarization using tool_use pattern
    - Persist episodic entry with embedding, upsert skill graph
    - Implement partial failure strategy (log and continue on non-critical failures)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 7. Implement Mentor Chat and Session End routers
  - [x] 7.1 Implement Mentor router (/api/mentor)
    - Create `app/routers/mentor.py` with POST endpoint accepting topic, mode, messages, optional sessionId
    - Wire context assembler, prompt store, and Anthropic API call
    - Include ImmediateContext from uploaded files when sessionId is provided
    - Return 400 if no profile exists
    - _Requirements: 7.1, 7.5, 7.6, 7.7, 7.8_

  - [x] 7.2 Implement Session End endpoint (/api/session/end)
    - Add POST /api/session/end endpoint that delegates to session_end service
    - Return session_id, title, summary, and skill_update
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 8. Implement Memory/Episodic endpoints
  - [x] 8.1 Implement Memory router (/api/memory/episodes)
    - Create `app/routers/memory.py` with POST /search (vector search), GET (paginated list), DELETE /{session_id}
    - Implement pagination with limit (1–100) and offset
    - Filter by user_id, optional topic filter
    - Return episodes with session_id, title, summary, topic, date, skill_update, score
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 8.2 Write property test for pagination bounds (Property 6)
    - **Property 6: Pagination Bounds**
    - Generate random limit/offset × data sizes → verify at most `limit` results, no duplicates/omissions
    - **Validates: Requirements 8.4**

- [x] 9. Checkpoint - Ensure mentor/memory tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Onboarding flow
  - [x] 10.1 Implement onboarding bootstrap service
    - Create `app/services/onboarding_bootstrap.py` with goal knowledge base lookup and LLM-based skill derivation
    - Generate skill nodes with required_level, current_level, and computed gap
    - _Requirements: 10.2, 10.3_

  - [x] 10.2 Implement Onboarding router (/api/onboarding)
    - Create `app/routers/onboarding.py` with POST /chat and POST /complete endpoints
    - Parse LLM response for suggestion chips (`json suggestions` block) and `onboarding_complete` JSON block
    - On /complete: upsert L1 profile, call bootstrap, return skill topics list
    - Handle LLM failures with 500 + empty text response
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4_

  - [ ]* 10.3 Write property test for onboarding response parsing (Property 7)
    - **Property 7: Onboarding Response Parsing**
    - Generate random LLM response strings with JSON blocks → verify extraction of suggestions array or onboarding_complete object
    - **Validates: Requirements 9.2, 9.3**

  - [ ]* 10.4 Write property test for bootstrap skill creation (Property 8)
    - **Property 8: Bootstrap Skill Creation**
    - Generate goals from KB keys → verify skill nodes created with valid required_level, current_level, and gap
    - **Validates: Requirements 10.3**

- [x] 11. Implement File Ingestion
  - [x] 11.1 Implement file upload and storage service
    - Create `app/services/file_upload.py` with file validation (type, size) and storage (local disk or S3 based on config)
    - Support PDF and CSV MIME types, reject others with HTTP 400 and per-file error details
    - _Requirements: 11.1, 11.2, 11.3, 13.4_

  - [x] 11.2 Implement extraction and chunking service
    - Create `app/services/extraction.py` with PDF text extraction (pypdf), CSV parsing, text chunking, and embedding storage
    - Process files as background tasks
    - _Requirements: 11.4_

  - [x] 11.3 Implement Ingestion router (/api/ingest)
    - Create `app/routers/ingest.py` with POST / (upload + create job, 201), GET /{job_id}/status, POST /trigger
    - Validate file types/sizes, store files, create job record, enqueue background extraction
    - Enforce job ownership (403), handle missing jobs (404)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

  - [ ]* 11.4 Write property test for file validation rejection (Property 9)
    - **Property 9: File Validation Rejection**
    - Generate files with random invalid MIME types or sizes exceeding max → verify HTTP 400 with per-file errors
    - **Validates: Requirements 11.1, 11.2**

- [x] 12. Checkpoint - Ensure onboarding and ingestion tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement Frontend Proxy and Backward Compatibility
  - [x] 13.1 Implement Next.js proxy utility
    - Create `lib/api-proxy.ts` in the Next.js app with `proxyToBackend(path, userId, init)` function
    - Attach X-User-Id and X-Api-Key headers
    - Handle unauthenticated users (return 401 without forwarding)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 13.2 Ensure backward-compatible response shapes
    - Verify all endpoint responses use camelCase field names where the current frontend expects them
    - Add Pydantic `model_config` with `alias_generator` or explicit Field aliases where needed
    - Validate that request body fields and query parameters match existing frontend expectations
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ]* 13.3 Write property test for backward-compatible response shapes (Property 10)
    - **Property 10: Backward-Compatible Response Shapes**
    - Verify response JSON shapes match documented contracts (same field names, same value types)
    - **Validates: Requirements 14.1, 14.2, 14.3**

- [x] 14. Integration wiring and final tests
  - [x] 14.1 Wire all routers into main.py and create test configuration
    - Finalize `app/main.py` with all router imports and registrations
    - Create `tests/conftest.py` with shared fixtures (test DB, auth headers, httpx AsyncClient)
    - Ensure MongoDB index creation in `_ensure_indexes()` for all collections
    - _Requirements: 1.2, 1.3, 13.1, 13.2_

  - [ ]* 14.2 Write integration tests for full request lifecycles
    - Create integration tests covering: profile CRUD flow, skills CRUD flow, session lifecycle, mentor chat with mocked Anthropic, onboarding flow, ingestion upload + status polling
    - Use httpx AsyncClient with FastAPI TestClient
    - _Requirements: 1.1, 3.1–3.5, 4.1–4.6, 5.1–5.6, 7.1–7.8, 9.1–9.4, 11.1–11.9_

  - [x] 14.3 Create Dockerfile and deployment configuration
    - Create `Dockerfile` with Python base image, dependency install, and uvicorn entrypoint on port 8000
    - Verify health check works in containerized environment
    - _Requirements: 1.1_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (Hypothesis library)
- Unit tests validate specific examples and edge cases
- The design uses Python (FastAPI) with async Motor — all implementations follow this stack
- Frontend proxy (task 13.1) is TypeScript since it lives in the Next.js app

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4"] },
    { "id": 3, "tasks": ["1.5", "3.1"] },
    { "id": 4, "tasks": ["3.2", "4.1", "4.4"] },
    { "id": 5, "tasks": ["3.3", "3.4", "4.2", "4.3", "4.5"] },
    { "id": 6, "tasks": ["6.1", "6.3"] },
    { "id": 7, "tasks": ["6.2", "6.4"] },
    { "id": 8, "tasks": ["7.1", "7.2", "8.1"] },
    { "id": 9, "tasks": ["8.2", "10.1"] },
    { "id": 10, "tasks": ["10.2", "11.1"] },
    { "id": 11, "tasks": ["10.3", "10.4", "11.2"] },
    { "id": 12, "tasks": ["11.3"] },
    { "id": 13, "tasks": ["11.4", "13.1", "13.2"] },
    { "id": 14, "tasks": ["13.3", "14.1"] },
    { "id": 15, "tasks": ["14.2", "14.3"] }
  ]
}
```
