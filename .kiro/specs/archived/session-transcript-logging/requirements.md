# Requirements Document

## Introduction

Session Transcript Logging captures the full raw conversation data from each AI interaction (onboarding chats and mentor sessions) for development analysis. Unlike the existing `messages` array on the Session model (which stores user-facing content only), transcripts include system prompts, raw Anthropic API responses, model metadata, and token usage — giving the team full visibility into how the AI harness behaves so they can iterate on prompt engineering and response quality.

## Glossary

- **Transcript_Logger**: The service responsible for capturing and persisting transcript entries during AI interactions
- **Transcript_Store**: The MongoDB collection that holds persisted transcript documents
- **Transcript_Entry**: A single logged exchange within a transcript, containing the request sent to the AI model and the raw response received
- **Session_Type**: The category of chat session — either `onboarding` or `mentor`
- **API_Route**: A Next.js route handler that processes chat requests (onboarding/chat or mentor)
- **Raw_Response**: The complete Anthropic API response object including content, model info, stop reason, and token usage

## Requirements

### Requirement 1: Capture Transcript on Each AI Call

**User Story:** As a developer, I want every AI interaction to be logged with full request and response data, so that I can analyze exactly what the model received and produced.

#### Acceptance Criteria

1. WHEN the API_Route sends a request to the Anthropic API, THE Transcript_Logger SHALL record the system prompt, user messages array, model name, max_tokens parameter, and the originating route identifier (e.g., "onboarding_chat" or "mentor") as the request payload of a new Transcript_Entry
2. WHEN the Anthropic API returns a response, THE Transcript_Logger SHALL record the full Raw_Response including content blocks, stop_reason, model identifier, and usage (input_tokens, output_tokens), and associate it with the corresponding request Transcript_Entry using a shared correlation ID
3. THE Transcript_Logger SHALL capture an ISO-8601 timestamp at the moment the Anthropic API request is sent (request_timestamp) and a second ISO-8601 timestamp at the moment the response or error is received (response_timestamp) for each Transcript_Entry
4. IF an Anthropic API call fails with an error, THEN THE Transcript_Logger SHALL record the error message and HTTP status code (or SDK error type if no status code is available) as the response payload of the corresponding Transcript_Entry
5. IF the Transcript_Logger fails to persist a Transcript_Entry, THEN THE API_Route SHALL continue processing and return the AI response to the caller without interruption, and log the persistence failure to the application error log

### Requirement 2: Persist Transcripts to MongoDB

**User Story:** As a developer, I want transcripts stored in a dedicated MongoDB collection, so that they don't bloat the existing sessions collection and can be queried independently.

#### Acceptance Criteria

1. THE Transcript_Store SHALL persist each transcript as a separate document in a dedicated `transcripts` collection
2. THE Transcript_Store SHALL associate each transcript document with a userId, a sessionId, and a createdAt timestamp, enforcing a unique constraint on sessionId so that at most one document exists per session
3. THE Transcript_Store SHALL associate each transcript document with a Session_Type (`onboarding` or `mentor`)
4. THE Transcript_Store SHALL store Transcript_Entry objects within each transcript document as an array ordered chronologically by each entry's timestamp (ascending)
5. WHEN a transcript document for the given sessionId already exists, THE Transcript_Store SHALL append new entries to the existing document's array rather than creating a duplicate
6. IF a persist or append operation is called with a missing or empty userId, sessionId, or Session_Type, THEN THE Transcript_Store SHALL reject the operation and report a validation error without writing to the collection

### Requirement 3: Include Session Context Metadata

**User Story:** As a developer, I want each transcript to carry session context (mode, topic, user profile snapshot), so that I can correlate prompt behavior with user characteristics without cross-referencing multiple collections.

#### Acceptance Criteria

1. WHEN a mentor session transcript is created, THE Transcript_Logger SHALL record the session mode as one of the enumerated values (planning, topic, doubt, evaluation) and the current topic string as provided in the request
2. IF a mentor session request does not include a topic value, THEN THE Transcript_Logger SHALL record the topic field as null
3. WHEN an onboarding session transcript is created, THE Transcript_Logger SHALL record the onboarding step context as the list of data-point field names already collected (from the set: goal, deadline, current_level, daily_availability)
4. THE Transcript_Logger SHALL record the model name and max_tokens value used for the AI call as metadata on each Transcript_Entry
5. WHEN a transcript document is created, THE Transcript_Logger SHALL record a snapshot of the user's core profile (goal, deadline, overall_level, daily_availability) at the time of creation

### Requirement 4: Enable Transcript Retrieval for Analysis

**User Story:** As a developer, I want to query transcripts by user, session, date range, and session type, so that I can pull relevant conversation data for prompt analysis.

#### Acceptance Criteria

1. WHEN a retrieval request includes a valid sessionId, THE Transcript_Store SHALL return the complete transcript matching that sessionId
2. IF no transcript exists for the provided sessionId, THEN THE Transcript_Store SHALL return null
3. WHEN a list request is made, THE Transcript_Store SHALL support filtering by any combination of userId, Session_Type (planning, topic, doubt, evaluation), startDate, and endDate, where each filter parameter is individually optional
4. THE Transcript_Store SHALL return a maximum of 100 transcripts per list query, accepting an optional limit parameter (1–100, default 50)
5. THE Transcript_Store SHALL return list results in reverse chronological order by createdAt
6. IF a list request specifies a startDate that is after the endDate, THEN THE Transcript_Store SHALL return an empty result set
7. THE Transcript_Store SHALL index the userId, sessionId, and createdAt fields for query performance

### Requirement 5: Control Logging via Environment Flag

**User Story:** As a developer, I want to enable or disable transcript logging via an environment variable, so that I can turn it off in production without code changes.

#### Acceptance Criteria

1. WHEN the environment variable `ENABLE_TRANSCRIPT_LOGGING` is set to the case-sensitive string `true`, THE Transcript_Logger SHALL capture and persist transcript data for that request
2. IF the environment variable `ENABLE_TRANSCRIPT_LOGGING` is absent or set to any value other than the case-sensitive string `true`, THEN THE Transcript_Logger SHALL skip all capture and persistence operations and SHALL NOT open connections or perform writes to the transcript store
3. THE Transcript_Logger SHALL evaluate the environment variable at the start of each incoming request, not at application startup, so that changes to the variable take effect on the next request without requiring a restart
4. WHEN the environment variable `ENABLE_TRANSCRIPT_LOGGING` is set to `true` and a request completes transcript capture, THE Transcript_Logger SHALL produce a log entry indicating that transcript persistence occurred for that request

### Requirement 6: Non-Blocking Logging

**User Story:** As a developer, I want transcript logging to not add latency to chat responses, so that the user experience remains unchanged.

#### Acceptance Criteria

1. THE Transcript_Logger SHALL persist transcript entries asynchronously without awaiting completion before the API_Route returns its response to the client
2. IF the Transcript_Logger encounters a persistence error, THEN THE Transcript_Logger SHALL log the error details including sessionId and error message to the application console and continue without altering the API response status code or body
3. THE Transcript_Logger SHALL add no more than 5ms of synchronous overhead to the API_Route request handling, measured as the wall-clock time between invoking the logging call and resuming execution of the response path
4. IF the Transcript_Logger has more than 50 pending persistence operations in memory, THEN THE Transcript_Logger SHALL drop new transcript entries and log a warning to the application console rather than allowing unbounded memory growth

### Requirement 7: Transcript Data Expiry

**User Story:** As a developer, I want old transcripts to be automatically cleaned up, so that development storage doesn't grow unbounded.

#### Acceptance Criteria

1. THE Transcript_Store SHALL apply a TTL (time-to-live) index on the `createdAt` field of transcript documents with a default expiry of 30 days
2. WHERE the environment variable `TRANSCRIPT_TTL_DAYS` is set to a valid integer between 1 and 365, THE Transcript_Store SHALL use the specified number of days as the TTL duration instead of the default
3. IF the environment variable `TRANSCRIPT_TTL_DAYS` is set to a non-integer, zero, or negative value, THEN THE Transcript_Store SHALL ignore the invalid value, apply the default 30-day TTL, and log a warning to the application console indicating the invalid configuration
