# Requirements Document

## Introduction

Session Persistence implements the full session save pipeline that writes conversation data to MongoDB throughout the session lifecycle. Currently, sessions appear in the sidebar but contain no messages — the conversation is never persisted, skill graph updates never fire, and narrative summaries are never generated. This feature builds the end-to-end persistence pipeline: session lifecycle management (active → ended), incremental message storage, LLM-generated narrative summaries, structured skill graph extraction, and vector embedding for episodic memory retrieval. This restores the layered-memory architecture (L1 + L2 + L3) from being effectively L1-only.

## Glossary

- **Session_Manager**: The service responsible for managing session lifecycle state transitions and coordinating persistence operations
- **Session_Document**: The MongoDB document representing a complete session, including messages, status, summary, and skill updates
- **Message_Store**: The component responsible for persisting conversation messages to the Session_Document in MongoDB
- **SessionSaveHandler**: The backend handler that orchestrates the session-end pipeline (summary generation, skill extraction, embedding)
- **Skill_Graph_Repo**: The repository that reads and writes skill graph nodes in MongoDB
- **Narrative_Summary**: An LLM-generated 3-5 sentence description of what happened in a session, optimized for future semantic search retrieval
- **Skill_Update**: A structured JSON object extracted from the session containing topic, current_level, gap, weak_areas, strong_areas, and optional mock_score
- **Embedding_Service**: The service that generates vector embeddings from narrative summaries via Voyage AI and stores them in the Vector DB
- **Auto_Checkpoint**: A periodic save of raw messages to MongoDB every N turns, preventing data loss on abrupt tab close
- **Session_Status**: The lifecycle state of a session — one of `active`, `ending`, or `ended`

## Requirements

### Requirement 1: Session Lifecycle Management

**User Story:** As a user, I want my session to have a proper lifecycle from creation to completion, so that the system knows when a session is active and when to trigger end-of-session processing.

#### Acceptance Criteria

1. WHEN a user starts a new chat session, THE Session_Manager SHALL create a Session_Document in MongoDB with status set to `active`, an empty messages array, a generated session_id (UUID v4), the user_id, and a created_at timestamp
2. WHEN a Session_Document is created with status `active`, THE Session_Manager SHALL return the session_id to the client for use in subsequent message persistence calls
3. WHEN the user explicitly ends a session or closes the browser tab, THE Session_Manager SHALL transition the Session_Document status from `active` to `ending` before initiating end-of-session processing
4. WHEN end-of-session processing completes successfully, THE Session_Manager SHALL transition the Session_Document status from `ending` to `ended` and record an ended_at timestamp
5. IF end-of-session processing fails, THEN THE Session_Manager SHALL transition the Session_Document status to `ended`, record the ended_at timestamp, log the failure reason, and return a success response to the client without waiting for retry or recovery
6. THE Session_Manager SHALL reject status transitions that do not follow the sequence `active → ending → ended` and return an error indicating the invalid transition
7. IF a Session_Document remains in `ending` status for longer than 60 seconds, THEN THE Session_Manager SHALL automatically transition it to `ended`, record the ended_at timestamp, and log a timeout failure reason
8. WHEN a user starts a new chat session while a previous Session_Document for that user has status `active` or `ending`, THE Session_Manager SHALL transition the previous session to `ended` with a timeout failure reason before creating the new session
9. IF a session creation request is missing user_id, THEN THE Session_Manager SHALL return an error indicating the missing required field without creating a Session_Document

### Requirement 2: Incremental Message Persistence

**User Story:** As a user, I want my conversation messages saved to the database as the chat progresses, so that my conversation is not lost if the browser closes unexpectedly.

#### Acceptance Criteria

1. WHEN a user sends a message and receives a mentor response, THE Message_Store SHALL append both the user message and the mentor response to the Session_Document messages array in MongoDB within 2 seconds of the final response token being generated
2. THE Message_Store SHALL persist each message with the fields: role (user or mentor), content (full text, maximum 50,000 characters), and timestamp (ISO-8601 UTC)
3. WHEN the Message_Store appends messages to a Session_Document, THE Message_Store SHALL use an atomic append operation to prevent race conditions with concurrent writes and SHALL preserve chronological order based on timestamp
4. IF the Message_Store fails to persist a message, THEN THE Message_Store SHALL retry the operation once after a 1-second delay using an idempotent write (matching on session_id and message timestamp) to prevent duplicate entries, and if the retry fails, log the error with the session_id and message content to the application error log
5. THE Message_Store SHALL persist messages only to Session_Documents with status `active`
6. IF a persist operation targets a Session_Document with status other than `active`, THEN THE Message_Store SHALL reject the operation and return an error indicating the session is no longer accepting messages
7. WHEN a Session_Document's messages array is retrieved, THE Message_Store SHALL return messages in chronological order by timestamp

### Requirement 3: Auto-Checkpoint for Crash Recovery

**User Story:** As a user, I want my conversation saved periodically during the session, so that an abrupt browser close does not lose my entire conversation.

#### Acceptance Criteria

1. WHEN the message count in the current session reaches a multiple of 6 messages (counting both user and mentor messages), THE Auto_Checkpoint SHALL save the full messages array (all messages from session start up to and including the triggering message) to the Session_Document
2. IF the periodic checkpoint save (criterion 1) fails, THEN THE Auto_Checkpoint SHALL retry the save once after a 1-second delay, and if the retry also fails, SHALL store the unsaved messages in localStorage keyed by session_id
3. WHEN a browser tab close event (beforeunload) fires during an active session, THE Auto_Checkpoint SHALL send a checkpoint request containing the session_id and all messages added since the last successful checkpoint to the backend within the beforeunload event window
4. IF the beforeunload checkpoint request fails or does not receive a response within 2 seconds, THEN THE Auto_Checkpoint SHALL store all messages added since the last successful checkpoint in localStorage keyed by session_id as a recovery fallback
5. WHEN a new session starts and localStorage contains recovery messages for a previous session_id, THE Session_Manager SHALL detect the orphaned data, deduplicate against messages already present in the corresponding Session_Document (matching on message timestamp and role), and append only the missing recovered messages in chronological order
6. WHEN orphaned messages are recovered from localStorage, THE Session_Manager SHALL trigger end-of-session processing (summary generation and skill extraction) for the recovered Session_Document before the new session's first LLM call completes
7. WHEN orphaned messages are successfully persisted to the Session_Document and end-of-session processing completes, THE Session_Manager SHALL delete the corresponding localStorage recovery entry for that session_id

### Requirement 4: LLM-Generated Narrative Summary

**User Story:** As a user, I want the system to generate an intelligent summary of my session, so that the mentor can recall what happened in past sessions and provide contextually relevant guidance.

#### Acceptance Criteria

1. WHEN a session transitions to status `ending` and the session transcript contains at least 2 messages, THE SessionSaveHandler SHALL send the session transcript (truncated to the most recent 40,000 characters if longer) to the LLM with instructions to produce a narrative_summary of 3-5 sentences describing what was studied, what was strong, and what was weak
2. THE SessionSaveHandler SHALL include the session topic and mode in the LLM prompt so the summary is contextually appropriate for future semantic search retrieval
3. WHEN the LLM returns the narrative_summary, THE SessionSaveHandler SHALL persist the summary text to the Session_Document summary field in MongoDB
4. IF the LLM call for summary generation fails after 3 total attempts (1 initial + 2 retries with 2-second delays between attempts), THEN THE SessionSaveHandler SHALL generate a fallback summary by concatenating the first and last user messages (truncated to a combined maximum of 300 characters) with the prefix "Session covered:" and persist this fallback to the Session_Document
5. THE SessionSaveHandler SHALL constrain the LLM summary generation call to a maximum of 500 output tokens and a timeout of 30 seconds per attempt
6. IF a session transitions to status `ending` and the session transcript contains fewer than 2 messages, THEN THE SessionSaveHandler SHALL persist the fallback text "Session ended before meaningful interaction occurred." to the Session_Document summary field without invoking the LLM

### Requirement 5: Skill Update Extraction

**User Story:** As a user, I want my skill graph to update automatically after each session, so that my dashboard reflects my actual progress without manual input.

#### Acceptance Criteria

1. WHEN a session transitions to status `ending`, THE SessionSaveHandler SHALL send the full session transcript to the LLM with instructions to extract a skill_update JSON object containing: topic (string), new_level (one of novice, easy, medium, medium+, hard, expert), gap (number 0–100), weak_areas (array of strings, max 10 items), strong_areas (array of strings, max 10 items), and eval_score (string or omitted)
2. WHEN the LLM returns a skill_update object, THE SessionSaveHandler SHALL validate the object against the SkillUpdateToolSchema Zod schema before writing
3. WHEN the skill_update passes Zod validation, THE Skill_Graph_Repo SHALL upsert the skill graph node for the specified topic by calling applyUpdate, merging the new_level, gap, weak_areas, and strong_areas values with the existing node
4. IF the LLM returns a skill_update that fails Zod validation, THEN THE SessionSaveHandler SHALL log the invalid payload with the session_id and skip the skill graph update without failing the overall session-end pipeline
5. IF the LLM call for skill extraction fails after 2 retry attempts (3 total calls), THEN THE SessionSaveHandler SHALL log the failure with session_id and continue the session-end pipeline without updating the skill graph
6. WHEN a skill graph node is upserted via applyUpdate, THE Skill_Graph_Repo SHALL set the last_studied field to the current ISO-8601 timestamp at the time of the update

### Requirement 6: Vector Embedding for Episodic Memory

**User Story:** As a user, I want my session summaries embedded and stored for semantic retrieval, so that the mentor can find relevant past experiences when I revisit a topic.

#### Acceptance Criteria

1. WHEN the narrative_summary is persisted to the Session_Document, THE Embedding_Service SHALL generate a vector embedding of the summary text using the configured embedding provider (Voyage AI)
2. WHEN the embedding is generated, THE Embedding_Service SHALL store the vector in the Vector DB with metadata including: user_id, session_id, topic, session mode, and the session ended_at date
3. IF the embedding provider API call fails after 3 retry attempts with exponential backoff (initial delay 1 second, maximum delay 8 seconds), THEN THE Embedding_Service SHALL log the failure with the session_id and enqueue the embedding for a delayed retry within 5 minutes, continuing without blocking the session-end pipeline
4. THE Embedding_Service SHALL process embedding generation asynchronously so that the session-end response is not blocked by embedding latency
5. WHEN a fallback summary is used (due to LLM summary failure), THE Embedding_Service SHALL still generate and store an embedding from the fallback text
6. IF the narrative_summary text is empty or contains fewer than 10 characters, THEN THE Embedding_Service SHALL skip embedding generation and log a warning with the session_id
7. IF an embedding for the same session_id already exists in the Vector DB, THEN THE Embedding_Service SHALL overwrite the existing vector and metadata rather than creating a duplicate entry
8. IF any required metadata field (user_id, session_id, topic, session mode, or ended_at) is missing at storage time, THEN THE Embedding_Service SHALL log the missing field names with the session_id and skip vector storage

### Requirement 7: Combined Session-End LLM Call

**User Story:** As a developer, I want the narrative summary and skill update extracted in a single LLM call, so that session-end processing is cost-efficient and fast.

#### Acceptance Criteria

1. THE SessionSaveHandler SHALL use a single LLM call to produce both the narrative_summary and the skill_update, returning them in a JSON object with two keys: `narrative_summary` (string) and `skill_update` (object)
2. WHEN the LLM response is received, THE SessionSaveHandler SHALL parse the response as JSON and extract the two fields independently
3. IF the LLM response is not valid JSON, THEN THE SessionSaveHandler SHALL attempt to extract the narrative_summary using a regex match for text between quotes after the key "narrative_summary", and log a warning about malformed JSON
4. IF the LLM response contains a valid narrative_summary but an invalid or missing skill_update, THEN THE SessionSaveHandler SHALL proceed with summary persistence and embedding while skipping the skill graph update
5. IF the LLM response contains a valid skill_update but an invalid or missing narrative_summary, THEN THE SessionSaveHandler SHALL proceed with the skill graph update and use the fallback summary strategy for persistence and embedding

### Requirement 8: Client-Side Session Wiring

**User Story:** As a user, I want the chat interface to properly communicate with the session persistence backend, so that my conversations are saved without any manual action.

#### Acceptance Criteria

1. WHEN the chat component mounts and no session_id is present in component state or localStorage, THE chat component SHALL call POST /api/sessions to create a new session and store the returned session_id in both component state and localStorage within 5 seconds of mount
2. WHEN the user sends a message and the mentor response stream completes, THE chat component SHALL send both messages (with role, content, and timestamp) to POST /api/sessions/{session_id}/messages using the stored session_id, and treat an HTTP 2xx response as confirmation of successful persistence
3. IF the message persistence call returns a non-2xx response or times out after 5 seconds, THEN THE chat component SHALL retry once after 1 second, and if the retry fails, queue the messages in localStorage keyed by session_id for recovery on next session load
4. WHEN the user clicks the End Session button, THE chat component SHALL call PATCH /api/sessions/{session_id} with status `ending` to trigger the session-end pipeline and display a loading indicator while awaiting the response
5. WHEN the session-end response is received with HTTP 2xx status, THE chat component SHALL clear the active session_id from component state and localStorage, and update the sidebar to show the completed session using the title field returned in the response body
6. IF the session-end call does not receive a response within 30 seconds, THEN THE chat component SHALL display an error message indicating session processing timed out and allow the user to retry the end-session action
7. THE chat component SHALL NOT clear localStorage message drafts until the backend returns an HTTP 2xx response confirming successful message persistence
8. IF the session creation call fails, THEN THE chat component SHALL retry once after 2 seconds, and if the retry fails, display an error message indicating the session could not be started and disable the message input until the user clicks a visible retry button
9. WHILE the session-end pipeline is processing (between sending the PATCH request and receiving the response), THE chat component SHALL disable the message input and the End Session button to prevent further interaction with the ending session
