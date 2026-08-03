# Requirements Document

## Introduction

This document captures the requirements for replacing the standalone session model with persistent topic-based conversations that support in-place compaction. Users create named topics, return to them across days, and the system automatically summarizes older messages when the conversation window approaches capacity. Skill graph updates fire at each compaction point to capture learning progress incrementally.

## Glossary

- **Topic**: A persistent conversation thread with a title, belonging to a single user, that can span multiple visits over time
- **TopicService**: The service responsible for topic CRUD operations, listing, and lifecycle state transitions
- **CompactionService**: The service that monitors token usage within a topic and orchestrates summarization when thresholds are crossed
- **SessionService**: The adapted service handling per-turn LLM calls within the context of a topic thread
- **ContextAssembler**: The service that assembles the full LLM context per call, reading from topic thread messages including summary blocks
- **TokenCounter**: A utility that estimates token counts for messages and the overall conversation window
- **SummaryBlock**: A data structure that replaces a range of compacted messages with a narrative summary
- **CompactionEvent**: An audit log entry recording the details of a compaction operation
- **Compaction_Threshold**: The configurable percentage of context window capacity (default 60%) at which compaction is triggered
- **SkillGraphService**: The existing service that manages skill graph updates based on learning progress
- **Topic_Sidebar**: The UI component displaying the user's list of topics ordered by last activity

## Requirements

### Requirement 1: Topic Creation

**User Story:** As a learner, I want to create named topic threads so that I can organize my learning conversations by subject and return to them over time.

#### Acceptance Criteria

1. WHEN a user sends the first message without an active topic, THE TopicService SHALL auto-create a new topic using the first 100 characters of the first message content (trimmed of whitespace) as the initial title and set its status to "active"
2. WHEN a user renames a topic, THE TopicService SHALL update the topic title to the new value provided it passes title validation
3. WHEN a user explicitly creates a topic with a title, THE TopicService SHALL create a new topic with status "active" and persist it to the database
4. THE TopicService SHALL validate that the topic title is between 1 and 100 characters after trimming whitespace
5. IF a topic title fails validation, THEN THE TopicService SHALL reject the operation and return an error indicating that the title must be between 1 and 100 non-whitespace-only characters
6. WHEN a topic is created, THE TopicService SHALL set the lastActiveAt timestamp to the creation time

### Requirement 2: Topic Listing and Navigation

**User Story:** As a learner, I want to see my topics in a sidebar so that I can quickly navigate between different learning threads.

#### Acceptance Criteria

1. WHEN the user opens the application, THE Topic_Sidebar SHALL display all active topics ordered by lastActiveAt descending, loading a maximum of 50 topics initially
2. THE Topic_Sidebar SHALL display each topic with its title (truncated to 60 characters with ellipsis if longer), last activity time as a relative timestamp (e.g., "2 min ago", "3 days ago"), and a message preview of the last message truncated to 80 characters
3. WHEN a topic is archived, THE Topic_Sidebar SHALL exclude the archived topic from the default listing
4. WHEN the user selects a topic from the sidebar, THE System SHALL navigate to that topic and display its conversation history starting with the most recent 50 messages
5. IF the user has no active topics, THEN THE Topic_Sidebar SHALL display an empty state message indicating no topics exist and prompting the user to start a new conversation
6. IF a topic fails to load when selected, THEN THE System SHALL display an error message indicating the topic could not be loaded and retain the user's current view

### Requirement 3: Topic Lifecycle Management

**User Story:** As a learner, I want to archive topics I've finished studying so that my sidebar stays uncluttered while preserving my conversation history.

#### Acceptance Criteria

1. WHEN a user archives a topic, THE TopicService SHALL set the topic status to "archived" and preserve all topic data including messages, summary blocks, and compaction events
2. IF a status transition other than "active" to "archived" is attempted, THEN THE TopicService SHALL reject the operation and return an error indicating the transition is not permitted
3. WHEN a topic is archived, THE System SHALL hide the topic from the home and sidebar default views
4. WHEN a user requests to view archived topics, THE System SHALL display a list of archived topics with their titles and last activity timestamps, ordered by lastActiveAt descending
5. THE TopicService SHALL retain all messages, summary blocks, and compaction events for archived topics without deletion

### Requirement 4: Message Handling Within Topics

**User Story:** As a learner, I want my messages to be appended to the current topic thread so that I can continue conversations across multiple visits.

#### Acceptance Criteria

1. WHEN a user sends a message within a topic, THE TopicService SHALL validate that the message content does not exceed 50,000 characters and append the message to the topic's messages array ordered by timestamp ascending
2. IF the topic's status is not "active", THEN THE TopicService SHALL reject the message append with an error indicating the topic is not accepting messages
3. WHEN the SessionService receives a message, THE SessionService SHALL assemble context via ContextAssembler and call the LLM for a response within a 30-second timeout
4. IF the LLM call fails or times out, THEN THE TopicService SHALL retain the user's message in the topic's messages array and return an error indicating the assistant response could not be generated
5. WHEN the LLM responds, THE TopicService SHALL append the assistant message to the topic's messages array with role set to "assistant" and timestamp set to the time of receipt
6. WHEN any message is appended, THE TopicService SHALL update the topic's lastActiveAt timestamp to the current time and recalculate currentTokenEstimate as the sum of estimated tokens across all messages in the topic's messages array

### Requirement 5: Token Counting and Capacity Monitoring

**User Story:** As a system operator, I want accurate token usage tracking so that compaction triggers at the right time without wasting context window budget.

#### Acceptance Criteria

1. WHEN a message is appended to a topic, THE TokenCounter SHALL estimate the token count using a character-to-token ratio heuristic and store the resulting integer token count with the message
2. THE TokenCounter SHALL calculate the available conversation capacity by subtracting the sum of fixed overhead allocations (system prompt, L1 Core Profile, L2 Skill Graph, L3 Episodic RAG, goal anchor) from the total context budget, where the total context budget is read from a configurable value defaulting to 200000 tokens
3. THE TokenCounter SHALL provide an integer usage percentage (0 to 100) representing tokens consumed by the conversation window relative to the available conversation capacity, recalculated each time a message is appended or a full recount occurs
4. WHEN the cached token estimate is older than 10 messages since last recalculation, THE TokenCounter SHALL perform a full recount by summing the stored token counts of all messages in the conversation array
5. IF the conversation window token count exceeds 80% of the available conversation capacity, THEN THE TokenCounter SHALL emit a compaction-needed signal indicating the current usage percentage and message count
6. IF the conversation window token count exceeds 100% of the available conversation capacity, THEN THE TokenCounter SHALL reject the new message append and return an over-capacity error indicating the current token count and the maximum allowed

### Requirement 6: Compaction Triggering

**User Story:** As a learner, I want the system to automatically manage conversation length so that I never lose context quality due to overly long threads.

#### Acceptance Criteria

1. WHEN the conversation window token usage exceeds the Compaction_Threshold, THE CompactionService SHALL trigger compaction by invoking the compaction execution flow
2. THE System SHALL provide a configurable Compaction_Threshold with a default value of 60% of the available conversation capacity, accepting values between 30% and 90% inclusive
3. WHEN a user navigates to a topic and the currentTokenEstimate exceeds 40% of capacity before any new message is appended, THE CompactionService SHALL trigger pre-emptive compaction
4. WHEN an assistant response is appended to the topic, THE SessionService SHALL invoke CompactionService.shouldCompact to evaluate whether compaction is needed
5. IF compaction is already in progress for a topic, THEN THE CompactionService SHALL skip the new compaction trigger and take no action until the in-progress compaction completes

### Requirement 7: Compaction Execution

**User Story:** As a learner, I want older messages to be automatically summarized so that my conversation thread remains coherent and within context limits.

#### Acceptance Criteria

1. WHEN compaction is triggered, THE CompactionService SHALL select the oldest non-summarized messages first for summarization, skipping any existing SummaryBlocks, until the selected messages' token total meets or exceeds the target token reclamation amount needed to bring conversation window usage below the Compaction_Threshold
2. THE CompactionService SHALL never split a user-assistant message pair during message selection; if including a pair would exceed the reclamation target, THE CompactionService SHALL still include the full pair
3. WHEN messages are selected for compaction, THE CompactionService SHALL call the LLM with a summarization prompt and a maximum output limit of 25% of the token count of the selected messages to produce a narrative summary
4. WHEN a summary is generated, THE CompactionService SHALL replace the compacted messages with a SummaryBlock containing the narrative summary text, the start and end timestamps of the compacted range, the list of compacted message identifiers, and the token count of the summary
5. THE CompactionService SHALL maintain strict chronological ordering of all messages and summary blocks after compaction by inserting the SummaryBlock at the position of the first compacted message
6. WHEN compaction succeeds, THE CompactionService SHALL record a CompactionEvent with tokens before, tokens after, tokens reclaimed, message count compacted, and the associated topic identifier
7. IF fewer than 2 complete user-assistant message pairs are available for selection, THEN THE CompactionService SHALL skip compaction and leave the thread unchanged

### Requirement 8: Skill Graph Updates at Compaction

**User Story:** As a learner, I want my learning progress captured incrementally during long conversations so that skill tracking stays current without waiting for a topic to end.

#### Acceptance Criteria

1. WHEN compaction is executed, THE CompactionService SHALL extract skill graph updates from the same summarization LLM call that produces the narrative summary, using structured output parsing to obtain zero or more skill node updates
2. IF the summarization LLM call returns no skill graph updates for the compacted messages, THEN THE CompactionService SHALL proceed with the summary block without writing to the SkillGraphService
3. WHEN skill updates are extracted, THE CompactionService SHALL pass them to the SkillGraphService for Zod schema validation and persistence
4. IF the skill graph update fails after compaction, THEN THE CompactionService SHALL preserve the summary block and queue the skill update for retry up to a maximum of 3 attempts
5. IF the queued skill update fails after 3 retry attempts, THEN THE CompactionService SHALL discard the update and log the failure for operator review

### Requirement 9: Context Assembly with Summary Blocks

**User Story:** As a learner, I want the AI to understand my full conversation history even after compaction so that responses remain contextually relevant.

#### Acceptance Criteria

1. WHEN assembling context for an LLM call, THE ContextAssembler SHALL include both raw messages and SummaryBlocks from the topic thread's messages array, treating each SummaryBlock's summary field as conversation content with a distinguishable role indicator
2. THE ContextAssembler SHALL position each SummaryBlock in the assembled conversation window according to its compactedRange.from timestamp, maintaining chronological order relative to surrounding raw messages
3. THE ContextAssembler SHALL inject L1 Core Profile, L2 Skill Graph, and L3 Episodic RAG data using the same retrieval and formatting logic as for conversations without compaction, with no modification to their content based on compaction state
4. THE ContextAssembler SHALL count each SummaryBlock's tokenCount toward the conversation window's token budget when calculating total context size
5. IF a SummaryBlock in the messages array fails Zod validation or has missing required fields, THEN THE ContextAssembler SHALL skip the malformed SummaryBlock, log a warning, and assemble the remaining context without it

### Requirement 10: Compaction Error Handling

**User Story:** As a system operator, I want compaction failures to be handled gracefully so that no messages are ever lost due to system errors.

#### Acceptance Criteria

1. IF the compaction LLM call fails (timeout, error response, or malformed output), THEN THE CompactionService SHALL preserve all original messages unchanged, skip compaction for the current turn, and retry on the next turn that crosses the Compaction_Threshold
2. IF compaction fails 3 consecutive times for a topic, THEN THE System SHALL display an in-app notification to the user indicating the thread is getting long and suggesting starting a new topic, and SHALL reset the consecutive failure counter to 0 upon the next successful compaction
3. THE CompactionService SHALL never remove messages from the thread until the replacement SummaryBlock has been successfully persisted to the database
4. IF a concurrent write conflict occurs on a topic, THEN THE TopicService SHALL refetch the document and retry the operation up to a maximum of 3 attempts using optimistic concurrency
5. IF the concurrent write conflict retry limit of 3 attempts is exhausted, THEN THE TopicService SHALL abort the operation, preserve the original message state, and return an error indicating a conflict failure

### Requirement 11: Compaction Visibility in UI

**User Story:** As a learner, I want a subtle indication when messages have been summarized so that I understand why older messages appear as summaries.

#### Acceptance Criteria

1. WHEN the chat UI renders a SummaryBlock, THE System SHALL display a collapsed indicator containing the label "earlier messages summarized" and the count of compacted messages
2. WHEN the chat UI renders a SummaryBlock, THE System SHALL display the compactedRange date range formatted as "MMM D – MMM D, YYYY" (or "MMM D, YYYY" if from and to fall on the same day) within the indicator
3. THE System SHALL render SummaryBlock indicators at a smaller font size than regular messages and with a muted background to distinguish them from user and assistant messages while maintaining inline placement within the conversation flow
4. WHEN the user clicks or taps a SummaryBlock indicator, THE System SHALL expand the indicator to reveal the full narrative summary text
5. WHEN the user clicks or taps an expanded SummaryBlock, THE System SHALL collapse it back to the compact indicator state

### Requirement 12: Existing Session Migration

**User Story:** As an existing user, I want my previous sessions migrated into the topic model so that I do not lose my conversation history.

#### Acceptance Criteria

1. WHEN the migration runs, THE System SHALL convert each existing session into a topic using the session's existing title if present, otherwise deriving a title from the session's detected mode and topic field (e.g., "Topic Session - Graphs")
2. WHEN migrating a session, THE System SHALL preserve all messages, timestamps, and ordering from the original session, and set the topic's userId to the session's user_id
3. WHEN migration completes for a session, THE System SHALL mark the migrated topic status as "active" with lastActiveAt set to the session's last message timestamp
4. THE System SHALL run the migration idempotently by using the original session_id as a stable lookup key so that re-running the migration skips sessions that have already been converted into topics
5. IF an existing session contains zero messages, THEN THE System SHALL skip that session during migration without creating a topic

### Requirement 13: Topic Data Integrity

**User Story:** As a system operator, I want topic data to remain consistent even under concurrent access so that no messages are lost or duplicated.

#### Acceptance Criteria

1. THE TopicService SHALL maintain strictly chronological ordering of the messages array such that each element's timestamp is greater than or equal to the preceding element's timestamp
2. THE TopicService SHALL ensure that a SummaryBlock is positioned in the messages array after all elements with timestamps earlier than its compactedRange.from and before all elements with timestamps later than its compactedRange.to
3. THE TopicService SHALL ensure that the union of all compactedMessageIds across summary blocks plus remaining raw messages equals the original full message set with no omissions and no duplicates
4. WHEN multiple clients access the same topic simultaneously, THE TopicService SHALL use a version field for optimistic concurrency control, rejecting writes where the version has changed since the document was read
5. IF a concurrent write conflict is detected, THEN THE TopicService SHALL refetch the document and retry the operation up to 3 times before returning an error indicating a conflict to the caller

### Requirement 14: Performance and Scalability

**User Story:** As a learner, I want topic operations to be fast so that my learning flow is not interrupted by system lag.

#### Acceptance Criteria

1. WHEN the main response stream completes, THE System SHALL initiate compaction asynchronously without blocking or delaying delivery of the streamed response to the user
2. THE Topic_Sidebar SHALL use projection queries that fetch only topicId, title, status, lastActiveAt, and a truncated last message limited to 100 characters
3. THE TokenCounter SHALL cache token counts at write time to avoid recalculation on every read
4. WHEN a topic accumulates more than 500 messages after compaction, THE System SHALL move summary blocks older than the most recent 50 messages to a separate collection and load them only when the user scrolls to that portion of the conversation
5. THE Topic_Sidebar SHALL return the topic list to the client within 500 milliseconds under normal database load

### Requirement 15: Security and Access Control

**User Story:** As a learner, I want my topic conversations to be private so that no one else can access my learning history.

#### Acceptance Criteria

1. THE System SHALL include the authenticated userId as a filter in every database query for topic operations, ensuring no query can return or modify topics belonging to a different user
2. WHEN an API request targets a topic that does not belong to the authenticated user, THE System SHALL return HTTP 403 without revealing whether the topic exists
3. IF a topic ID in a request does not match any topic in the system, THEN THE System SHALL return HTTP 404
4. THE CompactionService SHALL instruct the summarization LLM to summarize learning content without introducing personal information not already present in the conversation
5. THE System SHALL return identical error responses for "topic not found" and "topic belongs to another user" scenarios to prevent user enumeration through topic IDs
