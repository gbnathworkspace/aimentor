# Requirements Document

## Introduction

The Ingestion Pipeline is responsible for transforming raw user data into the structured and semantic memory stores that power MentorMan's mentoring capability. It runs at two trigger points: (1) during onboarding when the user uploads a resume PDF and LeetCode CSV, and (2) at the end of each mentoring session when the LLM produces a narrative summary and skill update. Additionally, the pipeline supports a two-phase checkpoint mechanism that prevents data loss on abrupt session closure.

## Glossary

- **Ingestion_Pipeline**: The backend service (FastAPI) that extracts, routes, and stores user data from file uploads and session-end LLM outputs into MongoDB and Atlas Vector Search.
- **File_Upload_Handler**: The component that validates, stores, and enqueues uploaded files for asynchronous processing.
- **Extractor_Service**: The component that routes files to the appropriate extractor (PDF or CSV) and returns parsed content.
- **PDF_Extractor**: The component that extracts section-aware text from resume PDF files using PyMuPDF.
- **CSV_Extractor**: The component that parses LeetCode CSV exports into aggregated per-topic difficulty counts using pandas.
- **Ingestion_Router**: The component that splits extracted content into structured and narrative paths for parallel processing.
- **Structured_Parser**: The component that transforms extracted content into typed facts (Core Profile fields, Skill Graph signals) and writes them to MongoDB with Zod validation.
- **Chunker_Service**: The component that splits narrative text into section-aware chunks suitable for embedding.
- **Embedder_Service**: The component that generates vector embeddings via Voyage AI and stores them in Atlas Vector Search.
- **Session_End_Processor**: The component that receives the LLM's dual output (narrative_summary + skill_update) at session end and routes each to the correct store.
- **Checkpoint_Service**: The component that manages the two-phase save mechanism: auto-checkpointing raw transcripts and triggering clean session-end summaries.
- **Core_Profile**: The MongoDB document containing the user's goal, deadline, availability, role, and YOE (Layer 1 memory).
- **Skill_Graph**: The MongoDB collection of per-topic proficiency nodes with signals like LeetCode counts and evaluation scores (Layer 2 memory).
- **Atlas_Vector_Search**: MongoDB Atlas's vector search capability used to store and retrieve embedded session summaries and resume narratives (Layer 3 memory).
- **Job_Record**: A MongoDB document tracking the status of an asynchronous ingestion job (`pending`, `processing`, `done`, `partial`, `failed`).

## Requirements

### Requirement 1: File Upload Validation and Storage

**User Story:** As a user completing onboarding, I want to upload my resume and LeetCode export so that MentorMan can understand my background and current skill level.

#### Acceptance Criteria

1. WHEN a file is uploaded, THE File_Upload_Handler SHALL validate that the file type is `application/pdf` or `text/csv`
2. WHEN a file is uploaded, THE File_Upload_Handler SHALL validate that the file size is greater than 0 bytes and does not exceed 10MB
3. IF an uploaded file has an unsupported type, THEN THE File_Upload_Handler SHALL reject the request with an HTTP 400 response and an error message indicating the supported file types (`application/pdf`, `text/csv`)
4. IF an uploaded file exceeds the size limit or is 0 bytes, THEN THE File_Upload_Handler SHALL reject the request with an HTTP 400 response indicating the maximum allowed size of 10MB
5. WHEN validation passes, THE File_Upload_Handler SHALL store the raw file to S3 under the path `uploads/{userId}/{jobId}/{filename}` with a 24-hour TTL
6. IF the S3 storage operation fails, THEN THE File_Upload_Handler SHALL return an HTTP 500 response and SHALL NOT create a Job_Record
7. WHEN the file is stored in S3, THE File_Upload_Handler SHALL create a Job_Record in MongoDB with status `pending` and the list of uploaded files
8. WHEN the Job_Record is created, THE File_Upload_Handler SHALL return the `jobId` to the client immediately without waiting for extraction to complete
9. WHEN a file upload request is received, THE File_Upload_Handler SHALL accept a maximum of 2 files per request

### Requirement 2: PDF Extraction

**User Story:** As a user, I want my resume content to be accurately extracted so that MentorMan can learn about my work history, education, and skills.

#### Acceptance Criteria

1. WHEN a PDF file is queued for processing, THE PDF_Extractor SHALL extract raw text from the file using PyMuPDF
2. WHEN text is extracted, THE PDF_Extractor SHALL detect section headings (Work Experience, Education, Skills, Projects) using regex and heuristics
3. WHEN sections are detected, THE PDF_Extractor SHALL return an array of section objects, each containing the section name and its text content
4. WHEN sections are extracted, THE PDF_Extractor SHALL preserve sub-headings (job titles, company names, degree names, project titles) within each section as distinct entries for downstream section-aware chunking
5. IF the PDF cannot be parsed, THEN THE PDF_Extractor SHALL mark the Job_Record as `failed` with an error message indicating the parsing failure reason
6. IF text extraction succeeds but yields no recognizable section headings, THEN THE PDF_Extractor SHALL treat the entire extracted text as a single section named "Unstructured" and return it for downstream processing
7. IF text extraction succeeds but the extracted content is empty or contains fewer than 10 characters, THEN THE PDF_Extractor SHALL mark the Job_Record as `failed` with an error message indicating that no readable text content was found in the PDF

### Requirement 3: CSV Extraction

**User Story:** As a user, I want my LeetCode progress to be parsed so that MentorMan can accurately assess my current skill level per topic.

#### Acceptance Criteria

1. WHEN a CSV file is queued for processing, THE CSV_Extractor SHALL parse the file using pandas with typed column definitions
2. THE CSV_Extractor SHALL validate that the required columns (`title`, `difficulty`, `status`, `topic`) exist in the CSV
3. IF required columns are missing, THEN THE CSV_Extractor SHALL mark the Job_Record as `failed` with the specific missing column names in the error message
4. WHEN the CSV is valid, THE CSV_Extractor SHALL filter rows to include only those with a `status` value of "Accepted" or "Solved"
5. WHEN filtered rows are available, THE CSV_Extractor SHALL aggregate them by `topic` and `difficulty` columns
6. THE CSV_Extractor SHALL recognize difficulty values of "Easy", "Medium", and "Hard" (case-insensitive) and discard rows with unrecognized difficulty values
7. THE CSV_Extractor SHALL return an array of objects with structure `{ topic, easy, medium, hard }` representing solved counts per topic per difficulty
8. IF a row has a missing or empty `topic` field, THEN THE CSV_Extractor SHALL skip that row and log a warning without failing the job

### Requirement 4: Content Routing

**User Story:** As a system operator, I want extracted content to be automatically routed to the correct storage path so that structured facts and narrative text are stored optimally for their retrieval patterns.

#### Acceptance Criteria

1. WHEN extraction completes for a LeetCode CSV, THE Ingestion_Router SHALL route the aggregated topic-difficulty data exclusively to the structured path for MongoDB storage, with no content sent to the narrative path
2. WHEN extraction completes for a resume, THE Ingestion_Router SHALL route the work history section to both the structured path (for role and YOE extraction) and the narrative path (for embedding), ensuring the full section text is available to both paths without modification
3. WHEN extraction completes for a resume, THE Ingestion_Router SHALL route the skills section exclusively to the structured path for Skill Graph tag population
4. WHEN extraction completes for a resume, THE Ingestion_Router SHALL route project description sections exclusively to the narrative path for embedding, with no content sent to the structured path
5. WHEN extraction completes for a resume, THE Ingestion_Router SHALL route the education section exclusively to the structured path for Core Profile population
6. WHEN routing completes, THE Ingestion_Router SHALL execute the structured path and the narrative path in parallel
7. IF extraction produces a section that does not match any defined routing rule (work history, skills, projects, education), THEN THE Ingestion_Router SHALL discard the unrecognized section and log a warning without failing the job
8. IF the narrative path fails after routing while the structured path succeeds, THEN THE Ingestion_Router SHALL mark the job status as "partial" and preserve all structured path writes
9. IF the structured path fails after routing, THEN THE Ingestion_Router SHALL mark the job status as "failed" and not proceed with narrative path writes for the same job

### Requirement 5: Structured Fact Parsing and Storage

**User Story:** As a user, I want my profile and skill data to be accurately stored so that MentorMan's mentoring is personalized from the first session.

#### Acceptance Criteria

1. WHEN LeetCode aggregates are received, THE Structured_Parser SHALL upsert per-topic signal documents to the Skill_Graph collection with the format `{ topic, signals: { leetcode_solved: { easy, medium, hard } } }`, creating a new document if the topic does not exist or merging signals into the existing document
2. WHEN resume structured content is received, THE Structured_Parser SHALL extract and write `currentRole`, `yearsOfExperience`, `education`, and `skills` to the Core_Profile document
3. IF the resume does not contain a recognizable value for `currentRole` or `yearsOfExperience`, THEN THE Structured_Parser SHALL set those fields to null in the Core_Profile document and log a warning without failing the job
4. THE Structured_Parser SHALL validate all writes against the Zod schema before persisting to MongoDB
5. IF Zod validation fails, THEN THE Structured_Parser SHALL reject the write, log the validation error with the specific field(s) that failed, and mark the Job_Record as `failed`
6. WHEN writing both Core_Profile and Skill_Graph documents for the same job, THE Structured_Parser SHALL execute both writes within a MongoDB transaction to ensure atomicity — either both succeed or neither is persisted

### Requirement 6: Section-Aware Chunking

**User Story:** As a user, I want my resume narrative to be chunked intelligently so that future semantic searches return coherent, contextually complete results.

#### Acceptance Criteria

1. THE Chunker_Service SHALL split narrative text by detected section headings (Work Experience, Education, Skills, Projects), keeping each work experience entry, project description, or education entry as a single chunk
2. THE Chunker_Service SHALL target a maximum chunk size of 512 tokens as measured by the tokenizer of the configured embedding model, but SHALL allow chunks to exceed this limit when splitting would break coherent content boundaries
3. WHEN a section exceeds 512 tokens and can be split without breaking content coherence, THE Chunker_Service SHALL split at sentence boundaries with an overlap of 50 tokens (approximately 10% of the maximum chunk size) between consecutive chunks
4. THE Chunker_Service SHALL attach metadata to each chunk containing `userId`, `source` (resume or session), `section` name, and a `chunkIndex` that is a zero-based integer incremented per section within the same document
5. WHERE a topic can be mapped from the chunk's section name or from matching chunk text against existing Skill Graph topic names, THE Chunker_Service SHALL include a `topic` tag in the metadata for downstream topic-filtered retrieval
6. IF the Chunker_Service cannot detect any recognized section headings in the input text, THEN THE Chunker_Service SHALL treat the entire input as a single unnamed section and apply the 512-token splitting rules with sentence-boundary splitting and 50-token overlap

### Requirement 7: Embedding and Vector Storage

**User Story:** As a user, I want my narrative content to be embedded and stored so that MentorMan can semantically retrieve relevant context during future sessions.

#### Acceptance Criteria

1. WHEN the Chunker_Service outputs processed chunks, THE Embedder_Service SHALL generate vector embeddings using the Voyage AI voyage-4-lite model producing 1536-dimension vectors
2. THE Embedder_Service SHALL process chunks in batches of up to 20 to stay within Voyage AI rate limits
3. WHEN embeddings are generated, THE Embedder_Service SHALL store each chunk with its vector, text, and metadata in the Atlas_Vector_Search collection, where metadata includes userId, source, section, chunkIndex, and topic_category
4. IF the Voyage AI API is unavailable, THEN THE Embedder_Service SHALL retry up to 3 times with exponential backoff starting at 1 second and capping at 8 seconds, and SHALL mark the job as `partial` when the retry limit is reached
5. WHEN the job is marked `partial`, THE Ingestion_Pipeline SHALL still complete the structured path — the user profile and skill graph are populated even if embedding fails
6. IF writing to the Atlas_Vector_Search collection fails after embeddings are generated, THEN THE Embedder_Service SHALL retry the storage operation up to 2 times before marking the job as `partial` and preserving the structured path results

### Requirement 8: Job Status Tracking

**User Story:** As a user completing onboarding, I want to see progress of my file processing so that I know when MentorMan is ready to mentor me.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL expose a `GET /api/ingest/{jobId}/status` endpoint that returns a JSON response containing `status`, `message`, and `completedAt` fields
2. THE Ingestion_Pipeline SHALL transition job status through the states: `pending` → `processing` → `done` (or `partial` or `failed`), where `pending` transitions to `processing` when extraction begins, and `processing` transitions to a terminal state when all paths complete or fail. Jobs SHALL NOT transition back to `processing` from terminal states — only `pending` → `processing` is permitted
3. WHEN a job reaches `partial` status, THE Ingestion_Pipeline SHALL include a message explaining that structured data was saved but embedding failed
4. WHEN a job reaches `failed` status, THE Ingestion_Pipeline SHALL include a user-facing error message describing the failure reason
5. THE Ingestion_Pipeline SHALL update the Job_Record status atomically at each state transition to prevent inconsistent reads
6. IF a request is made for a `jobId` that does not exist, THEN THE Ingestion_Pipeline SHALL return an HTTP 404 response
7. THE Ingestion_Pipeline SHALL only allow a user to query the status of their own jobs — requests for another user's jobId SHALL return HTTP 403

### Requirement 9: Session-End Ingestion

**User Story:** As a user, I want my session learnings to be captured and stored automatically when a session ends so that MentorMan remembers what we covered.

#### Acceptance Criteria

1. WHEN a session ends, THE Session_End_Processor SHALL receive the LLM's JSON output containing `narrative_summary` and `skill_update` fields
2. IF the LLM output is malformed or missing required fields (`narrative_summary` or `skill_update`), THEN THE Session_End_Processor SHALL log the malformed response, mark the session as `orphaned` for retry, and preserve the raw transcript
3. WHEN a narrative_summary is received, THE Session_End_Processor SHALL pass the text to the Embedder_Service for embedding via Voyage AI
4. WHEN the narrative_summary embedding is generated, THE Session_End_Processor SHALL store it in Atlas_Vector_Search with metadata including `userId`, `sessionId`, `date`, `type` (session type), `topic`, and `topic_category`
5. WHEN a skill_update is received, THE Session_End_Processor SHALL validate it against the Skill_Graph Zod schema
6. IF Zod validation of the skill_update fails, THEN THE Session_End_Processor SHALL log the validation error and skip the skill graph write without affecting the narrative_summary embedding — the write SHALL be skipped even if logging itself fails, prioritizing data integrity
7. WHEN validation passes, THE Session_End_Processor SHALL upsert the skill_update into the Skill_Graph collection, merging new signals with existing values for the matched topic node
8. WHEN the skill_update contains omitted fields (e.g., no `mock_score` for a non-evaluation session), THE Session_End_Processor SHALL preserve the existing values for those fields during the merge
9. IF the Embedder_Service fails during session-end ingestion, THEN THE Session_End_Processor SHALL discard the narrative_summary, still attempt the skill_update write, and mark the session as `partial`

### Requirement 10: Auto-Checkpoint (Phase 1)

**User Story:** As a user, I want my conversation to be periodically saved so that if my browser crashes or I accidentally close the tab, my session data is not lost.

#### Acceptance Criteria

1. WHEN the conversation reaches every 5th turn (where one turn is one user message plus one assistant response), THE Checkpoint_Service SHALL initiate a save of the raw session transcript to MongoDB (the save is fire-and-forget — initiating the process is sufficient)
2. THE Checkpoint_Service SHALL perform checkpoint saves without making an LLM call and SHALL complete the save operation within 2 seconds
3. THE Checkpoint_Service SHALL overwrite the session document's `transcript` field with the complete ordered list of messages from session start through the current turn at each checkpoint
4. WHEN a checkpoint save completes successfully, THE Checkpoint_Service SHALL update the session document's `last_checkpoint_turn` field with the integer turn number of the most recently persisted turn
5. IF the MongoDB write fails during a checkpoint save, THEN THE Checkpoint_Service SHALL retry the write once after a 1-second delay and SHALL not interrupt the user's active conversation regardless of save outcome

### Requirement 11: Clean Session End (Phase 2)

**User Story:** As a user, I want a proper session summary generated when I intentionally end a session so that my skill graph and episodic memory are accurately updated.

#### Acceptance Criteria

1. WHEN the user closes the tab or clicks the end-session control, THE Checkpoint_Service SHALL send a `POST /session/end` request via the `beforeunload` event within 2 seconds of the trigger
2. WHEN the session-end request is received, THE Checkpoint_Service SHALL invoke the session summarization LLM call that produces a JSON response containing `narrative_summary` (3–5 sentences) and `skill_update` (matching the Skill Graph Zod schema), and the LLM SHALL respond within 30 seconds as a hard constraint — exceeding this limit constitutes a failure
3. IF the LLM call fails or does not respond within 30 seconds, THEN THE Checkpoint_Service SHALL mark the session as `orphaned` and preserve the raw transcript so that summary generation can be retried on the next session start
4. WHEN a valid LLM response is received, THE Checkpoint_Service SHALL route the `narrative_summary` to Atlas_Vector_Search (with metadata: topic, date, type, topic_category) and the `skill_update` to MongoDB via the Session_End_Processor
5. WHEN both writes complete successfully, THE Checkpoint_Service SHALL mark the session document as `ended` with an `ended_at` timestamp

### Requirement 12: Orphaned Session Recovery

**User Story:** As a user, I want sessions that were interrupted without a clean end to be properly summarized so that no learning progress is lost.

#### Acceptance Criteria

1. WHEN a new session is started, THE Checkpoint_Service SHALL always query for orphaned session documents belonging to that user (sessions with checkpoint data but no `ended_at` timestamp and no `summary`) created within the last 7 days, filtering results after retrieval
2. WHEN one or more orphaned sessions are detected, THE Checkpoint_Service SHALL process each orphaned session sequentially by running the session summarization LLM call on its transcript, completing all recoveries before the new session becomes active
3. WHEN the orphaned session summary is generated, THE Checkpoint_Service SHALL route the outputs through the Session_End_Processor to update Atlas_Vector_Search and Skill_Graph
4. WHEN recovery processing for an orphaned session completes successfully, THE Checkpoint_Service SHALL mark that session as `ended` with a `recovered: true` flag and set the `ended_at` timestamp to the recovery time
5. IF the summarization LLM call fails during orphaned session recovery, THEN THE Checkpoint_Service SHALL skip that orphaned session, log the failure, retain the checkpoint data unmodified for retry on the next session start, and proceed to load the new session

### Requirement 13: Re-Ingestion Handling

**User Story:** As a user, I want to re-upload an updated resume or LeetCode export so that MentorMan's understanding of me stays current.

#### Acceptance Criteria

1. WHEN a user uploads a file whose source category (resume or leetcode) matches a previously ingested file for that user, THE Ingestion_Pipeline SHALL set the job status to `processing`, treat the upload as a re-ingestion, and delete all existing vector chunks tagged with that source category before storing the newly generated chunks
2. WHEN re-ingestion occurs for structured data, THE Structured_Parser SHALL fully replace all previously stored structured facts originating from that source category with the new parsed values, without merging with prior values
3. WHILE re-ingestion is in progress, THE Ingestion_Pipeline SHALL preserve all embeddings and skill graph updates tagged with source "session" — only data tagged with the file source category being re-ingested is deleted and replaced
4. IF deletion of old data succeeds but the new ingestion job fails, THEN THE Ingestion_Pipeline SHALL mark the job as failed, restore the previously deleted vector chunks and structured facts from the retained raw file in S3, and surface an error indicating re-ingestion failure to the user
5. WHEN re-ingestion completes successfully, THE Ingestion_Pipeline SHALL update the job record status to "done" within 30 seconds of the final write and record a timestamp indicating when the source category was last re-ingested
