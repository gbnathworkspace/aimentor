# Requirements Document

## Introduction

This specification covers the consolidation of all MentorMan backend logic into a single unified FastAPI (Python) service. Currently, backend responsibilities are scattered across three codebases: Next.js API routes (TypeScript), the ingestion-pipeline (FastAPI/Python), and the layered-memory-service (FastAPI/Python). After consolidation, the Next.js application becomes a thin frontend that proxies authenticated requests to the unified FastAPI backend running on port 8000.

## Glossary

- **Unified_Backend**: The single consolidated FastAPI application that serves all backend API logic for MentorMan
- **Frontend_Proxy**: The Next.js application layer that handles authentication via Clerk, extracts the userId, and forwards requests to the Unified_Backend with an X-User-Id header
- **L1_Profile**: The core user profile layer (goal, deadline, overall_level, daily_availability)
- **L2_Skill_Graph**: The skill graph layer containing per-topic skill nodes with levels, gaps, and signals
- **L3_Episodic_Memory**: The episodic memory layer storing session summaries as vector-embedded documents for semantic retrieval
- **Context_Assembler**: The service that gathers L1 profile, L2 skill data, and L3 episodic results to build the mentor's system prompt context
- **Ingestion_Pipeline**: The file processing subsystem that handles upload, extraction (PDF/CSV), chunking, and embedding storage
- **Session_End_Processor**: The service that generates session summaries via LLM, persists episodic entries, and updates skill graphs
- **Onboarding_Bootstrap**: The service that auto-generates initial skill graph nodes from a user's stated goal
- **Clerk**: The third-party authentication provider used by the frontend
- **Checkpoint_Service**: The service within the ingestion-pipeline that handles session-end summarization with recovery semantics

## Requirements

### Requirement 1: Unified FastAPI Application Structure

**User Story:** As a developer, I want all backend logic consolidated into a single FastAPI application, so that deployment, debugging, and maintenance are simplified.

#### Acceptance Criteria

1. THE Unified_Backend SHALL expose all API endpoints on a single port (8000)
2. THE Unified_Backend SHALL include routers for profile, skills, sessions, mentor chat, onboarding, ingestion, and health check
3. THE Unified_Backend SHALL use a lifespan handler to manage MongoDB connection lifecycle (connect on startup, disconnect on shutdown)
4. THE Unified_Backend SHALL return a health check response at GET /health

### Requirement 2: Authentication and Authorization via Header

**User Story:** As a developer, I want the Unified_Backend to authenticate requests using a trusted header from the Frontend_Proxy, so that auth logic remains in Next.js while the backend enforces user isolation.

#### Acceptance Criteria

1. THE Unified_Backend SHALL require an X-User-Id header on all protected endpoints
2. IF a request lacks the X-User-Id header, THEN THE Unified_Backend SHALL return HTTP 401
3. THE Unified_Backend SHALL require an X-Api-Key header matching the configured secret for service-to-service authentication
4. IF the X-Api-Key header is missing or invalid, THEN THE Unified_Backend SHALL return HTTP 401
5. THE Unified_Backend SHALL use the X-User-Id value to scope all data access to that user

### Requirement 3: L1 Profile CRUD

**User Story:** As a user, I want to create, read, update, and delete my core profile, so that MentorMan understands my learning goals.

#### Acceptance Criteria

1. WHEN a GET request is received at /api/profile, THE Unified_Backend SHALL return the L1_Profile for the authenticated user
2. IF no profile exists for the user, THEN THE Unified_Backend SHALL return HTTP 404
3. WHEN a PUT request is received at /api/profile with valid profile fields, THE Unified_Backend SHALL update and return the updated profile
4. WHEN a DELETE request is received at /api/profile, THE Unified_Backend SHALL remove the profile for the authenticated user
5. WHEN a POST request is received at /api/profile with valid profile data, THE Unified_Backend SHALL create and return the new profile with HTTP 201

### Requirement 4: L2 Skill Graph CRUD

**User Story:** As a user, I want to manage my skill graph nodes, so that MentorMan tracks my progress across topics.

#### Acceptance Criteria

1. WHEN a GET request is received at /api/skills, THE Unified_Backend SHALL return all L2_Skill_Graph nodes for the authenticated user
2. WHEN a GET request is received at /api/skills/{topic}, THE Unified_Backend SHALL return the skill node for that topic
3. IF the topic does not exist in the user's skill graph, THEN THE Unified_Backend SHALL return HTTP 404
4. WHEN a POST request is received at /api/skills with valid skill data, THE Unified_Backend SHALL upsert the skill node and return it with HTTP 201
5. WHEN a PUT request is received at /api/skills/{topic} with update data, THE Unified_Backend SHALL update the skill node and return the updated node
6. WHEN a DELETE request is received at /api/skills/{topic}, THE Unified_Backend SHALL remove the skill node for that topic

### Requirement 5: Session Management

**User Story:** As a user, I want to create, list, retrieve, and save sessions, so that my mentoring history is preserved.

#### Acceptance Criteria

1. WHEN a GET request is received at /api/sessions with an optional limit parameter, THE Unified_Backend SHALL return the user's sessions ordered by creation date descending
2. WHEN a POST request is received at /api/sessions with title, mode, and topic, THE Unified_Backend SHALL create a new session record and return the sessionId with HTTP 201
3. WHEN a GET request is received at /api/sessions/{sessionId}, THE Unified_Backend SHALL return the full session including messages
4. IF the session does not belong to the authenticated user, THEN THE Unified_Backend SHALL return HTTP 403
5. IF the session does not exist, THEN THE Unified_Backend SHALL return HTTP 404
6. WHEN a PATCH request is received at /api/sessions/{sessionId} with messages, mode, and topic, THE Unified_Backend SHALL generate a summary via LLM, extract and apply skill updates, persist the messages, and return success

### Requirement 6: Session End Processing

**User Story:** As a user, I want the system to automatically summarize my session when it ends, so that meaningful episodic memories are stored for future context retrieval.

#### Acceptance Criteria

1. WHEN a POST request is received at /api/session/end with user_id, topic, and messages, THE Session_End_Processor SHALL generate a structured summary (title + narrative) via LLM
2. THE Session_End_Processor SHALL persist the summary as an L3_Episodic_Memory entry with a vector embedding
3. WHEN the LLM produces a skill_update in the summary, THE Session_End_Processor SHALL upsert the L2_Skill_Graph node with the new level and signal data
4. THE Session_End_Processor SHALL return the session_id, title, summary, and skill_update in the response

### Requirement 7: Mentor Chat with Context Assembly

**User Story:** As a user, I want to chat with my AI mentor who has full context about my profile, skills, and past sessions, so that mentoring is personalized and continuous.

#### Acceptance Criteria

1. WHEN a POST request is received at /api/mentor with topic, mode, messages, and optional sessionId, THE Unified_Backend SHALL assemble context from L1_Profile, L2_Skill_Graph, and L3_Episodic_Memory
2. THE Context_Assembler SHALL retrieve the user's profile from L1_Profile
3. THE Context_Assembler SHALL retrieve the relevant skill node from L2_Skill_Graph for the given topic
4. THE Context_Assembler SHALL perform a vector search on L3_Episodic_Memory using the last user message as query, returning up to 3 relevant past sessions
5. THE Unified_Backend SHALL format the assembled context into a system prompt using the appropriate mode template (planning, topic, doubt, or evaluation)
6. WHEN a sessionId is provided, THE Unified_Backend SHALL include uploaded file context (ImmediateContext) in the system prompt
7. THE Unified_Backend SHALL send the assembled prompt and messages to the Anthropic API and return the assistant's text response
8. IF the user has no profile, THEN THE Unified_Backend SHALL return HTTP 400 with a message indicating onboarding is required

### Requirement 8: L3 Episodic Memory (Vector Search)

**User Story:** As a user, I want my past session summaries to be semantically searchable, so that the mentor can recall relevant past interactions.

#### Acceptance Criteria

1. THE Unified_Backend SHALL store session summaries with vector embeddings generated by Voyage AI
2. WHEN a search query is received at /api/memory/episodes/search with query, limit, and optional topic, THE Unified_Backend SHALL perform a MongoDB Atlas vector search filtered by user_id
3. THE Unified_Backend SHALL return matching episodes with session_id, title, summary, topic, date, skill_update, and relevance score
4. WHEN a GET request is received at /api/memory/episodes with optional limit, offset, and topic, THE Unified_Backend SHALL return paginated episodic entries
5. WHEN a DELETE request is received at /api/memory/episodes/{session_id}, THE Unified_Backend SHALL remove the episode

### Requirement 9: Onboarding Chat

**User Story:** As a new user, I want to have a conversational onboarding experience, so that MentorMan learns about my goals naturally.

#### Acceptance Criteria

1. WHEN a POST request is received at /api/onboarding/chat with messages, THE Unified_Backend SHALL send the messages to the Anthropic API with the onboarding system prompt
2. THE Unified_Backend SHALL parse the LLM response for suggestion chips and return them alongside the text
3. WHEN the LLM emits an onboarding_complete JSON block, THE Unified_Backend SHALL extract the profile data and include it in the response with complete=true
4. IF the LLM call fails, THEN THE Unified_Backend SHALL return HTTP 500 with an empty text response

### Requirement 10: Onboarding Complete and Skill Bootstrap

**User Story:** As a new user, I want my initial skill graph auto-generated from my stated goal, so that I have a starting structure without manual setup.

#### Acceptance Criteria

1. WHEN a POST request is received at /api/onboarding/complete with goal, deadline, overall_level, and daily_availability, THE Unified_Backend SHALL upsert the user's L1_Profile
2. WHEN a profile is created during onboarding, THE Onboarding_Bootstrap SHALL derive skill topics from a goal knowledge base lookup or LLM generation
3. THE Onboarding_Bootstrap SHALL upsert L2_Skill_Graph nodes for each derived topic with required_level, current_level, and computed gap
4. THE Unified_Backend SHALL return the list of bootstrapped skill topics in the response

### Requirement 11: File Ingestion (Upload, Extract, Embed)

**User Story:** As a user, I want to upload PDF and CSV files, so that their content is extracted, chunked, and stored for use as mentoring context.

#### Acceptance Criteria

1. WHEN a POST request is received at /api/ingest with files and X-User-Id header, THE Ingestion_Pipeline SHALL validate file types and sizes
2. IF any file is invalid, THEN THE Ingestion_Pipeline SHALL return HTTP 400 with per-file error details
3. THE Ingestion_Pipeline SHALL store validated files in the configured storage backend (local disk or S3)
4. THE Ingestion_Pipeline SHALL create a job record in MongoDB and enqueue extraction as a background task
5. THE Ingestion_Pipeline SHALL return the job_id immediately with HTTP 201 for status polling
6. WHEN a GET request is received at /api/ingest/{job_id}/status, THE Ingestion_Pipeline SHALL return the current job status, message, and completion timestamp
7. IF the job does not exist, THEN THE Ingestion_Pipeline SHALL return HTTP 404
8. IF the requesting user does not own the job, THEN THE Ingestion_Pipeline SHALL return HTTP 403
9. WHEN a POST request is received at /api/ingest/trigger with a job_id, THE Ingestion_Pipeline SHALL enqueue extraction for an existing job record

### Requirement 12: Frontend Proxy Layer

**User Story:** As a developer, I want the Next.js app to act as a thin authenticated proxy to the Unified_Backend, so that the frontend handles auth and the backend handles all business logic.

#### Acceptance Criteria

1. THE Frontend_Proxy SHALL extract the userId from Clerk authentication on every request
2. THE Frontend_Proxy SHALL forward requests to the Unified_Backend at the configured MENTORMAN_API_BASE URL
3. THE Frontend_Proxy SHALL include the X-User-Id header with the authenticated userId on all forwarded requests
4. THE Frontend_Proxy SHALL include the X-Api-Key header with the configured service secret on all forwarded requests
5. THE Frontend_Proxy SHALL return the Unified_Backend's response status and body directly to the client
6. IF the user is not authenticated, THEN THE Frontend_Proxy SHALL return HTTP 401 without forwarding the request

### Requirement 13: Database and Configuration

**User Story:** As a developer, I want the Unified_Backend to use a single MongoDB connection and centralized configuration, so that environment management is straightforward.

#### Acceptance Criteria

1. THE Unified_Backend SHALL connect to MongoDB Atlas using the MONGODB_URI environment variable
2. THE Unified_Backend SHALL use Motor (async MongoDB driver) for all database operations
3. THE Unified_Backend SHALL read API keys and configuration from environment variables (ANTHROPIC_API_KEY, VOYAGE_API_KEY, MENTORMAN_API_KEY, STORAGE_BACKEND, S3_BUCKET_NAME)
4. THE Unified_Backend SHALL support both local disk and S3 storage backends configured via STORAGE_BACKEND environment variable
5. IF a required environment variable is missing at startup, THEN THE Unified_Backend SHALL fail fast with a descriptive error message

### Requirement 14: Backward Compatibility

**User Story:** As a developer, I want the Unified_Backend's API contract to match existing frontend expectations, so that the migration does not break the UI.

#### Acceptance Criteria

1. THE Unified_Backend SHALL maintain the same request and response JSON shapes as the current Next.js API routes for all migrated endpoints
2. THE Unified_Backend SHALL use camelCase field names in responses where the current Next.js routes use camelCase
3. THE Unified_Backend SHALL accept the same request body fields and query parameters as the current Next.js routes
4. WHEN the skill graph update uses string levels (beginner, intermediate, advanced, expert), THE Unified_Backend SHALL accept both string levels and the numeric gap format used by the frontend
