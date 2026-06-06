# Tasks: Ingestion Pipeline

## Task 1: Project Setup and Data Models

Set up the FastAPI project structure for the ingestion pipeline with all shared data models, schemas, and configuration.

- [x] 1.1 Create the FastAPI project skeleton with `app/`, `app/models/`, `app/services/`, `app/routers/`, `app/config/`, and `tests/` directories. Add `requirements.txt` with dependencies: fastapi, uvicorn, pymupdf (fitz), pandas, motor (async MongoDB), boto3, voyageai, pydantic, hypothesis, pytest, pytest-asyncio.
- [x] 1.2 Create `app/config/settings.py` with environment-based configuration for MongoDB URI, S3 bucket, Voyage AI API key, and LLM endpoint. Use pydantic `BaseSettings` for validation.
- [x] 1.3 Create `app/models/schemas.py` with all Pydantic/Zod-equivalent data models: `JobRecord`, `IngestionJobResponse`, `FileValidationError`, `ResumeSection`, `LeetCodeTopicStats`, `Chunk`, `ChunkMetadata`, `CoreProfileIngestion`, `SkillGraphSignals`, `LeetCodeCounts`, `VectorChunk`, `SessionCheckpoint`, `SessionEndOutput`, `IngestionStatus` enum (pending, processing, done, partial, failed).
- [x] 1.4 Create `app/models/validators.py` implementing Zod-style validation functions for Core Profile writes, Skill Graph writes, and session embedding metadata. Each validator raises `ValidationError` with specific field names on failure.
- [x] 1.5 Create `app/config/database.py` with MongoDB client initialization (motor async driver), S3 client initialization (boto3), and connection helpers for `ingestion_jobs`, `users`, `skill_graph`, `sessions`, and `embeddings` collections.

## Task 2: File Upload Handler

Implement the file upload endpoint that validates files, stores to S3, creates job records, and returns immediately.

- [x] 2.1 Create `app/services/file_upload_handler.py` implementing `FileUploadHandler` class with `handle_upload(user_id, files)` method. Validate file count (max 2), MIME types (application/pdf, text/csv), and sizes (0 < size <= 10MB). Return appropriate `FileValidationError` on failure.
- [x] 2.2 Implement S3 upload logic within `FileUploadHandler`: generate UUID jobId, construct S3 key as `uploads/{userId}/{jobId}/{filename}`, upload raw bytes. On S3 failure, return HTTP 500 without creating a Job_Record.
- [x] 2.3 Implement Job_Record creation in MongoDB with status='pending' and file metadata. Enqueue extraction as a FastAPI background task. Return `IngestionJobResponse` with jobId immediately.
- [x] 2.4 Create `app/routers/ingest.py` with `POST /api/ingest` endpoint wiring up the FileUploadHandler. Include proper error handling returning HTTP 400 for validation errors, HTTP 500 for S3 failures.

## Task 3: PDF Extractor

Implement section-aware PDF text extraction using PyMuPDF.

- [x] 3.1 Create `app/services/extractors/pdf_extractor.py` implementing `PDFExtractor` class with `extract(file_bytes) -> list[ResumeSection]`. Use PyMuPDF (fitz) to extract raw text from PDF bytes.
- [x] 3.2 Implement section heading detection using regex patterns for Work Experience, Education, Skills, and Projects headings. Support common variations (e.g., "WORK EXPERIENCE", "Professional Experience", "Employment History").
- [x] 3.3 Implement sub-heading preservation within sections (job titles, company names, project names). Parse the text between headings into ordered entries.
- [x] 3.4 Handle edge cases: if no sections detected → return single "Unstructured" sec tion; if extracted text < 10 chars → raise `ExtractionError`.

## Task 4: CSV Extractor

Implement LeetCode CSV parsing and aggregation using pandas.

- [x] 4.1 Create `app/services/extractors/csv_extractor.py` implementing `CSVExtractor` class with `extract(file_bytes) -> list[LeetCodeTopicStats]`. Parse CSV with pandas using typed column definitions.
- [x] 4.2 Implement required column validation: check for `title`, `difficulty`, `status`, `topic`. On missing columns, raise error with specific missing column names.
- [x] 4.3 Implement row filtering: include only rows where status is "Accepted" or "Solved" (case-insensitive). Discard rows with unrecognized difficulty (not Easy/Medium/Hard case-insensitive). Skip rows with empty topic (log warning).
- [x] 4.4 Implement aggregation by (topic, difficulty) → count. Return array of `LeetCodeTopicStats` objects with `{ topic, easy, medium, hard }`.

## Task 5: Extractor Service

Implement the routing layer that dispatches files to the correct extractor based on MIME type.

- [x] 5.1 Create `app/services/extractor_service.py` implementing `ExtractorService` class with `extract(job) -> ExtractionResult`. Route `application/pdf` to PDFExtractor and `text/csv` to CSVExtractor.
- [x] 5.2 Define `ExtractionResult` dataclass containing optional `resume_sections: list[ResumeSection]` and optional `leetcode_stats: list[LeetCodeTopicStats]`. Handle extraction errors by marking job as 'failed'.

## Task 6: Ingestion Router

Implement content routing that splits extracted data into structured and narrative paths.

- [x] 6.1 Create `app/services/ingestion_router.py` implementing `IngestionRouter` class with `route(extraction_result, job)` method. Implement routing rules: LeetCode → structured only; work_experience → both paths; skills → structured only; projects → narrative only; education → structured only; unrecognized → discard + log warning.
- [x] 6.2 Implement parallel execution of structured and narrative paths using `asyncio.gather`. If structured fails → mark job 'failed', skip narrative. If narrative fails after structured succeeds → mark job 'partial'.

## Task 7: Structured Parser

Implement structured fact extraction and MongoDB writes with validation and transactions.

- [x] 7.1 Create `app/services/structured_parser.py` implementing `StructuredParser` class with `process(leetcode_stats, resume_sections, user_id, job_id)` method.
- [x] 7.2 Implement LeetCode-to-Skill-Graph transformation: upsert per-topic signal docs with format `{ topic, signals: { leetcode_solved: { easy, medium, hard } } }`.
- [x] 7.3 Implement resume structured extraction: extract `currentRole`, `yearsOfExperience`, `education`, `skills` from resume sections. Set null for unrecognizable fields (log warning).
- [x] 7.4 Implement Zod validation gate: validate all data against Pydantic schemas before writes. On validation failure → reject write, mark job 'failed'.
- [x] 7.5 Implement MongoDB transaction wrapping: execute Core_Profile + Skill_Graph writes within a single transaction for atomicity.

## Task 8: Chunker Service

Implement section-aware text chunking with token limits and overlap.

- [x] 8.1 Create `app/services/chunker_service.py` implementing `ChunkerService` class with `chunk(sections, user_id, source) -> list[Chunk]`. Split by section headings, keeping each entry as a single chunk when ≤512 tokens.
- [x] 8.2 Implement token counting using a tokenizer compatible with the Voyage AI model. Implement sentence boundary splitting with 50-token overlap for chunks exceeding 512 tokens.
- [x] 8.3 Implement metadata attachment: `userId`, `source`, `section`, `chunkIndex` (zero-based per section), `topic` (mapped from section name or text matching), `job_id`.
- [x] 8.4 Handle edge case: if no recognized section headings → treat as single unnamed section, apply standard splitting rules.

## Task 9: Embedder Service

Implement vector embedding generation via Voyage AI and storage in Atlas Vector Search.

- [x] 9.1 Create `app/services/embedder_service.py` implementing `EmbedderService` class with `embed_and_store(chunks) -> None`. Process chunks in batches of 20.
- [x] 9.2 Implement Voyage AI API integration: call voyage-4-lite model, receive 1536-dimension vectors. Implement retry logic: up to 3 retries with exponential backoff (1s, 2s, 4s, cap 8s).
- [x] 9.3 Implement Atlas Vector Search storage: store (vector, text, metadata) for each chunk. Implement storage retry: up to 2 retries. On final failure → raise `EmbeddingError`.

## Task 10: Session End Processor

Implement session-end ingestion of LLM narrative summaries and skill updates.

- [x] 10.1 Create `app/services/session_end_processor.py` implementing `SessionEndProcessor` class with `process(user_id, session_id, llm_output)` method.
- [x] 10.2 Implement input validation: check for `narrative_summary` and `skill_update` fields. If malformed → mark session 'orphaned', preserve raw transcript.
- [x] 10.3 Implement narrative embedding: pass narrative_summary to EmbedderService with session metadata (userId, sessionId, date, type, topic, topic_category).
- [x] 10.4 Implement skill update: validate against Skill Graph schema, upsert into skill_graph collection merging new signals. Preserve existing field values for omitted fields. If validation fails → skip write, log error.
- [x] 10.5 Implement partial failure handling: if embedding fails → still attempt skill_update write, mark session 'partial'.

## Task 11: Checkpoint Service

Implement the two-phase checkpoint mechanism for session data preservation.

- [x] 11.1 Create `app/services/checkpoint_service.py` implementing `CheckpointService` class with `auto_checkpoint(session_id, messages)`, `end_session(session_id, user_id)`, and `recover_orphaned_sessions(user_id)` methods.
- [x] 11.2 Implement auto-checkpoint (Phase 1): trigger every 5th turn, overwrite session transcript field, update last_checkpoint_turn. No LLM call, complete within 2 seconds. On failure → retry once after 1s, never interrupt conversation.
- [x] 11.3 Implement clean session end (Phase 2): invoke summarization LLM (30s timeout), route narrative_summary → EmbedderService, route skill_update → SessionEndProcessor. Mark session 'ended' with timestamp. On LLM failure/timeout → mark 'orphaned', preserve transcript.
- [x] 11.4 Create `app/routers/session.py` with `POST /session/end` endpoint wiring up the CheckpointService session end flow.

## Task 12: Orphaned Session Recovery

Implement recovery of sessions that closed without a clean end.

- [x] 12.1 Implement `recover_orphaned_sessions(user_id)` in CheckpointService: query sessions with no `ended_at`, no `summary`, checkpoint data exists, created within last 7 days.
- [x] 12.2 Process orphaned sessions sequentially: run summarization LLM on transcript, route outputs through SessionEndProcessor. On success → mark 'ended' with `recovered=True`. On failure → skip, log, retain for next retry.
- [x] 12.3 Ensure all recoveries complete before new session becomes active by calling recovery at session start.

## Task 13: Re-Ingestion Handler

Implement re-upload handling with full replace semantics and rollback on failure.

- [x] 13.1 Create `app/services/reingestion_handler.py` implementing `ReIngestionHandler` class with `handle(user_id, source_category, job)` method.
- [x] 13.2 Implement deletion of old data: delete all vector chunks tagged with source_category, delete all structured facts from source_category. Preserve all 'session'-tagged data.
- [x] 13.3 Implement new ingestion execution: run normal pipeline for new files after deletion.
- [x] 13.4 Implement rollback on failure: if new ingestion fails → restore deleted data from S3 raw file. Update job record with `last_reingested_at` timestamp on success.

## Task 14: Job Status Tracking Endpoint

Implement the job status polling endpoint with authorization.

- [x] 14.1 Create `GET /api/ingest/{jobId}/status` endpoint in `app/routers/ingest.py`. Return JSON with `status`, `message`, and `completedAt` fields.
- [x] 14.2 Implement authorization: only allow users to query their own jobs (HTTP 403 for other users' jobs). Return HTTP 404 for non-existent jobIds.
- [x] 14.3 Implement status-specific messages: for 'partial' → explain structured data saved but embedding failed; for 'failed' → include user-facing error reason.

## Task 15: Job Status State Machine

Implement atomic job status transitions following the defined state machine.

- [x] 15.1 Create `app/services/job_status_machine.py` implementing valid transition logic: `pending → processing`, `processing → done`, `processing → partial`, `processing → failed`. Reject all other transitions.
- [x] 15.2 Implement atomic status updates in MongoDB to prevent inconsistent reads during transitions.

## Task 16: Property-Based Tests — File Upload Validation (Properties 1–2)

Write Hypothesis property-based tests for file upload validation and S3 path construction.

- [x] 16.1 [PBT] Create `tests/unit/test_file_validation.py`. Implement Property 1: File upload validation — for any file upload, validation accepts if and only if MIME type is in `{'application/pdf', 'text/csv'}` AND `0 < size <= 10,485,760`. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 1: File upload validation`
  **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
- [x] 16.2 [PBT] In same file, implement Property 2: S3 path construction — for any valid userId, jobId, and filename, the constructed S3 key equals `uploads/{userId}/{jobId}/{filename}`. Tag: `# Feature: ingestion-pipeline, Property 2: S3 path construction`
  **Validates: Requirements 1.5**

## Task 17: Property-Based Tests — PDF Extraction (Property 3)

Write Hypothesis property-based test for PDF section detection.

- [x] 17.1 [PBT] Create `tests/unit/test_pdf_extractor.py`. Implement Property 3: PDF section detection — for any text block with recognized section headings, the extractor returns section objects with non-empty section names and text, and the union covers the entire input. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 3: PDF section detection`
  **Validates: Requirements 2.2, 2.3**

## Task 18: Property-Based Tests — CSV Extraction (Properties 4–5)

Write Hypothesis property-based tests for CSV parsing and validation.

- [x] 18.1 [PBT] Create `tests/unit/test_csv_extractor.py`. Implement Property 4: CSV aggregation correctness — for any valid CSV, aggregated output per topic equals the filtered, grouped count by (topic, difficulty). Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 4: CSV aggregation correctness`
  **Validates: Requirements 3.4, 3.5, 3.6, 3.7, 3.8**
- [x] 18.2 [PBT] In same file, implement Property 5: CSV required column validation — validator accepts if and only if all four required columns exist, and error lists exactly the missing ones. Tag: `# Feature: ingestion-pipeline, Property 5: CSV required column validation`
  **Validates: Requirements 3.2, 3.3**

## Task 19: Property-Based Tests — Content Routing (Property 6)

Write Hypothesis property-based test for ingestion routing correctness.

- [x] 19.1 [PBT] Create `tests/unit/test_ingestion_router.py`. Implement Property 6: Content routing correctness — for any extraction result, verify routing rules: LeetCode → structured only, work_experience → both, skills → structured only, projects → narrative only, education → structured only, unrecognized → neither. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 6: Content routing correctness`
  **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.7**

## Task 20: Property-Based Tests — Structured Parser (Properties 7–8)

Write Hypothesis property-based tests for structured parsing and validation gating.

- [x] 20.1 [PBT] Create `tests/unit/test_structured_parser.py`. Implement Property 7: LeetCode to Skill Graph format — for any topic aggregate, the upsert document has format `{ topic, signals: { leetcode_solved: { easy, medium, hard } } }` with matching values. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 7: LeetCode to Skill Graph format`
  **Validates: Requirements 5.1**
- [x] 20.2 [PBT] In same file, implement Property 8: Zod validation gates all writes — for any data object, write succeeds if and only if it passes schema validation; invalid objects rejected without persisting. Tag: `# Feature: ingestion-pipeline, Property 8: Zod validation gates all writes`
  **Validates: Requirements 5.4, 5.5, 9.5**

## Task 21: Property-Based Tests — Chunker Service (Properties 9–12)

Write Hypothesis property-based tests for chunking logic.

- [x] 21.1 [PBT] Create `tests/unit/test_chunker_service.py`. Implement Property 9: Chunk size invariant — every output chunk has token count ≤ 512. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 9: Chunk size invariant`
  **Validates: Requirements 6.2**
- [x] 21.2 [PBT] In same file, implement Property 10: Section-aware chunking preserves entries — entries ≤512 tokens appear as single chunks without splitting. Tag: `# Feature: ingestion-pipeline, Property 10: Section-aware chunking preserves entries`
  **Validates: Requirements 6.1**
- [x] 21.3 [PBT] In same file, implement Property 11: Sentence boundary splitting with overlap — chunks from text >512 tokens overlap by ~50 tokens and split at sentence boundaries. Tag: `# Feature: ingestion-pipeline, Property 11: Sentence boundary splitting with overlap`
  **Validates: Requirements 6.3**
- [x] 21.4 [PBT] In same file, implement Property 12: Chunk metadata completeness — every chunk has non-null userId, source, section (or unnamed), and zero-based chunkIndex. Tag: `# Feature: ingestion-pipeline, Property 12: Chunk metadata completeness`
  **Validates: Requirements 6.4**

## Task 22: Property-Based Tests — Embedder Service (Properties 13–14)

Write Hypothesis property-based tests for embedding batch logic and retry backoff.

- [x] 22.1 [PBT] Create `tests/unit/test_embedder_service.py`. Implement Property 13: Embedding batch size invariant — N chunks partitioned into ⌈N/20⌉ batches, each ≤20 chunks, union equals original set. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 13: Embedding batch size invariant`
  **Validates: Requirements 7.2**
- [x] 22.2 [PBT] In same file, implement Property 14: Exponential backoff calculation — for retry n ∈ {0,1,2}, delay = min(2^n * 1, 8) seconds. Tag: `# Feature: ingestion-pipeline, Property 14: Exponential backoff calculation`
  **Validates: Requirements 7.4**

## Task 23: Property-Based Tests — Job Status (Property 15)

Write Hypothesis property-based test for job status state machine transitions.

- [x] 23.1 [PBT] Create `tests/unit/test_job_status.py`. Implement Property 15: Job status valid transitions — transitions accepted if and only if following valid paths (pending→processing, processing→done/partial/failed). All other transitions rejected. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 15: Job status valid transitions`
  **Validates: Requirements 8.2, 8.5**

## Task 24: Property-Based Tests — Session End Processor (Properties 16–18)

Write Hypothesis property-based tests for session-end processing logic.

- [x] 24.1 [PBT] Create `tests/unit/test_session_end_processor.py`. Implement Property 16: Malformed session output detection — JSON missing narrative_summary or skill_update marks session orphaned and preserves transcript. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 16: Malformed session output detection`
  **Validates: Requirements 9.2**
- [x] 24.2 [PBT] In same file, implement Property 17: Session embedding metadata completeness — session-end embeddings have non-null userId, sessionId, date, type, topic, topic_category. Tag: `# Feature: ingestion-pipeline, Property 17: Session embedding metadata completeness`
  **Validates: Requirements 9.4**
- [x] 24.3 [PBT] In same file, implement Property 18: Skill update merge preserves existing fields — incoming updates with omitted fields retain existing values while updating present fields. Tag: `# Feature: ingestion-pipeline, Property 18: Skill update merge preserves existing fields`
  **Validates: Requirements 9.7, 9.8**

## Task 25: Property-Based Tests — Checkpoint Service (Properties 19–21)

Write Hypothesis property-based tests for checkpoint trigger and correctness.

- [x] 25.1 [PBT] Create `tests/unit/test_checkpoint_service.py`. Implement Property 19: Checkpoint trigger interval — auto-checkpoint triggered if and only if turn N is a positive multiple of 5. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 19: Checkpoint trigger interval`
  **Validates: Requirements 10.1**
- [x] 25.2 [PBT] In same file, implement Property 20: Checkpoint correctness — after checkpoint at turn N with messages M, transcript equals M and last_checkpoint_turn equals N. Tag: `# Feature: ingestion-pipeline, Property 20: Checkpoint correctness`
  **Validates: Requirements 10.3, 10.4**
- [x] 25.3 [PBT] In same file, implement Property 21: Orphaned session query correctness — query returns exactly sessions with null ended_at, null summary, existing checkpoint data, created within 7 days. Tag: `# Feature: ingestion-pipeline, Property 21: Orphaned session query correctness`
  **Validates: Requirements 12.1**

## Task 26: Property-Based Tests — Re-Ingestion (Properties 22–24)

Write Hypothesis property-based tests for re-ingestion correctness.

- [x] 26.1 [PBT] Create `tests/unit/test_reingestion.py`. Implement Property 22: Re-ingestion deletes only source-category data — deletion removes chunks matching source C and preserves all others. Use `@settings(max_examples=100)`. Tag: `# Feature: ingestion-pipeline, Property 22: Re-ingestion deletes only source-category data`
  **Validates: Requirements 13.1**
- [x] 26.2 [PBT] In same file, implement Property 23: Re-ingestion full replace semantics — resulting structured data contains only new values, no residuals from prior ingestion. Tag: `# Feature: ingestion-pipeline, Property 23: Re-ingestion full replace semantics`
  **Validates: Requirements 13.2**
- [x] 26.3 [PBT] In same file, implement Property 24: Re-ingestion preserves session-tagged data — all session-tagged embeddings and skill updates remain unmodified in count, content, and metadata. Tag: `# Feature: ingestion-pipeline, Property 24: Re-ingestion preserves session-tagged data`
  **Validates: Requirements 13.3**
