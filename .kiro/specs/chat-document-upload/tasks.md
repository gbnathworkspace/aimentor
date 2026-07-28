# Implementation Plan: Chat Document Upload

## Overview

This plan implements the chat-based document upload feature for MentorMan. The pipeline allows users to upload documents (PDF, DOCX, CSV, XLSX, JSON, TXT, MD, RTF) directly from the chat interface, extracts text content, synthesizes structured L1 memory facts via LLM, and presents them for user confirmation before writing to the Core Profile. The implementation is split into backend (Python/FastAPI) and frontend (React/TypeScript) work, with the backend pipeline being fully independent from the existing onboarding `IngestionService`.

## Tasks

- [x] 1. Set up project structure, dependencies, and data models
  - [x] 1.1 Install backend dependencies and create module structure
    - Install `python-docx>=0.8.11`, `openpyxl>=3.1.0`, `striprtf>=0.0.26` via pip/requirements.txt
    - Create `app/routers/documents.py`, `app/services/document_extractor.py`, `app/services/l1_fact_synthesizer.py`, `app/services/document_pipeline.py`
    - Create `tests/property/` directory for property-based tests
    - _Requirements: 8.1, 8.2_

  - [x] 1.2 Define the `DocumentUploadJob` and `UploadFileRecord` data models
    - Create the `DocumentUploadJob` Pydantic model with fields: `job_id`, `user_id`, `status` (Literal["pending", "extracting", "synthesizing", "done", "failed"]), `files` (list of `UploadFileRecord`), `skip_review`, `message`, `extracted_text`, `proposals`, `proposal_count`, `created_at`, `updated_at`, `expires_at`
    - Create the `UploadFileRecord` model with fields: `filename`, `mime_type`, `file_path`, `size_bytes`, `status` (Literal["pending", "extracted", "failed"]), `error`
    - Create the `L1SynthesisOutput` and `SynthesizedStyleNote` response models for LLM output parsing
    - Set up the `document_upload_jobs` MongoDB collection with a TTL index on `expires_at`
    - _Requirements: 2.6, 2.7, 7.5, 8.6_

  - [x] 1.3 Extend `PendingProfileChange` usage for document-upload source tagging
    - Add `source_type="document_upload"` tagging when creating `PendingProfileChange` entries from document uploads
    - Use the `session_id` field to store the `job_id` for traceability
    - Ensure the existing `accept_pending_change` and `dismiss_pending_change` paths work with these tagged entries
    - _Requirements: 5.1, 5.4_

- [x] 2. Implement the document upload endpoint and file validation
  - [x] 2.1 Create `documents_router.py` with the upload endpoint
    - Register a new `APIRouter` at prefix `/api/documents/` with tag "Documents"
    - Implement `POST /api/documents/upload` accepting `multipart/form-data` with fields: `files` (up to 5), `skip_review` (bool, default false), `message` (optional string)
    - Add `Depends(require_auth)` for authentication — return HTTP 401 if unauthenticated
    - Validate each file's MIME type against `SUPPORTED_MIME_TYPES` and size against 10 MB limit
    - If batch exceeds 5 files, return HTTP 400 indicating maximum batch size
    - If all files fail validation, return HTTP 400 with per-file error details
    - If at least one file passes, store valid files, create `Upload_Job` with status `pending`, return HTTP 202 with `jobId`, `acceptedFiles` count, and `rejectedFiles` list
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Implement file storage with 24-hour TTL
    - Store uploaded files to `uploads/{userId}/{jobId}/` on local disk
    - Set the `expires_at` field on the `Upload_Job` to `created_at + 24 hours`
    - Implement a cleanup mechanism (background task or TTL-based) to delete expired files
    - _Requirements: 2.7, 9.5_

  - [x] 2.3 Implement the job status polling endpoint
    - Implement `GET /api/documents/jobs/{job_id}/status` returning the current `Upload_Job` state
    - Include `jobId`, `status`, per-file statuses, `proposals` (when done), `failedFiles`, and `createdAt`
    - Authenticate the request and ensure users can only access their own jobs
    - _Requirements: 6.1, 6.10_

  - [x] 2.4 Write property test for server-side batch validation (Property 3)
    - **Property 3: Server-side batch validation accepts valid subset and rejects invalid**
    - Generate random file batches (0–10 files, mixed valid/invalid sizes and MIME types)
    - Assert: batch > 5 files → 400; all invalid → 400; at least one valid → 202 with correct counts
    - **Validates: Requirements 2.3, 2.4, 2.5, 2.6**

- [x] 3. Implement multi-format document extraction
  - [x] 3.1 Implement PDF extraction
    - Extract text preserving paragraph boundaries as double newlines and section headings as prefixed lines
    - Handle corrupted/unreadable PDFs by marking file as `failed` with appropriate error
    - Handle password-protected PDFs by marking file as `failed` with "password-protected" error
    - _Requirements: 3.1, 3.9, 3.10_

  - [x] 3.2 Implement DOCX extraction
    - Extract headings, paragraphs, and list items from DOCX files using `python-docx`
    - Discard formatting metadata (font, color, spacing)
    - Handle corrupted/password-protected files with appropriate error marking
    - _Requirements: 3.2, 3.9, 3.10_

  - [x] 3.3 Implement CSV and XLSX extraction
    - Parse CSV files with column headers and row values, limiting to 5000 rows maximum
    - Parse XLSX files (first sheet) with column headers and row values, limiting to 5000 rows maximum using `openpyxl`
    - Discard rows beyond the limit while preserving headers
    - _Requirements: 3.3, 3.4_

  - [x] 3.4 Implement JSON extraction
    - Flatten JSON structure into key-path and value text representation
    - Traverse nested objects up to 10 levels deep, ignoring deeper content
    - Truncate arrays to the first 100 elements
    - _Requirements: 3.5_

  - [x] 3.5 Implement TXT, MD, and RTF extraction
    - Read TXT and MD files as UTF-8, replacing invalid byte sequences with U+FFFD
    - Strip RTF formatting using `striprtf` and extract plain text content
    - _Requirements: 3.6, 3.7_

  - [x] 3.6 Implement the extraction orchestrator and text truncation
    - Create `extract_document()` function that routes to the appropriate extractor based on MIME type
    - Mark files producing no usable text as `failed` with "no extractable content" error
    - Process each file independently so one failure does not block others
    - Truncate extracted text to 50,000 characters at the nearest sentence boundary
    - _Requirements: 3.8, 3.11, 3.12_

  - [x] 3.7 Write property tests for extraction (Properties 4, 5, 6, 7, 8, 9)
    - **Property 4: Tabular extraction respects row limits** — random CSV/XLSX data (0–10,000 rows), assert output ≤ 5000 rows with headers preserved
    - **Property 5: JSON flattening respects depth and array limits** — recursive JSON (0–15 levels, arrays 0–200 elements), assert depth ≤ 10 and arrays ≤ 100
    - **Property 6: UTF-8 text extraction replaces invalid bytes** — random byte sequences, assert valid UTF-8 output with U+FFFD replacements
    - **Property 7: RTF extraction preserves text content** — random text in RTF wrappers, assert original text recovered
    - **Property 8: Independent file processing** — mixed valid/corrupted batches, assert valid files succeed regardless of failures
    - **Property 9: Text truncation at sentence boundary** — random text 50,000–200,000 chars, assert output ≤ 50,000 chars ending at sentence boundary
    - **Validates: Requirements 3.3, 3.4, 3.5, 3.6, 3.7, 3.11, 3.12, 9.4**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement LLM-powered L1 fact synthesis
  - [x] 5.1 Implement the L1 fact synthesizer
    - Create `synthesize_l1_facts()` that sends combined extracted text to LLM with a system prompt instructing production of structured L1 field proposals
    - Truncate combined text to fit within 8000 tokens at sentence boundary before LLM call
    - Parse LLM response into `L1SynthesisOutput` schema (goal_orientation, learning_context_structured, style_notes, focus_areas)
    - Validate proposed `learning_context_structured` keys against `ALLOWED_STRUCTURED_KEYS` for the user's current `learning_context` — discard invalid keys
    - Validate `style_note` entries have `source_quote` ≤ 200 characters (verbatim from text)
    - Validate `focus_areas` entries are ≤ 60 characters each
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [x] 5.2 Implement accumulation logic and deduplication
    - Compare proposed `focus_areas` against existing focus areas using case-insensitive exact match — discard duplicates
    - When user has 5 existing style notes, flag proposals for replacement flow (do not silently overwrite)
    - Ensure proposals are additive — never overwrite or remove existing L1 field values
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 5.3 Implement LLM error handling and retry logic
    - If LLM produces no actionable proposals, mark job as `done` with "no memory updates found" result
    - If LLM call fails (timeout, rate limit, service error), retry once after 2-second delay
    - If retry fails, mark job as `failed` with specific error reason; preserve `extracted_text` on job record
    - If LLM response doesn't conform to schema, discard proposals, log failure, mark job `failed`
    - _Requirements: 4.7, 4.8, 4.9, 9.5_

  - [x] 5.4 Write property tests for synthesis validation (Properties 10, 11, 12, 14, 15)
    - **Property 10: Token-based truncation at sentence boundary** — random text 8,000–30,000 tokens, assert fits within 8000 tokens ending at sentence boundary
    - **Property 11: LLM output schema validation** — random JSON conforming/violating schema, assert correct accept/reject behavior
    - **Property 12: Allowed structured keys validation** — random key-value pairs × all LearningContext values, assert only allowed keys pass
    - **Property 14: Accumulation invariant** — random existing profiles + random proposals, assert no existing values lost
    - **Property 15: Focus area deduplication** — random strings with case variations, assert no case-insensitive duplicates
    - **Validates: Requirements 4.3, 4.5, 4.9, 7.1, 7.2**

- [x] 6. Implement the document pipeline orchestrator
  - [x] 6.1 Create `document_pipeline.py` background task
    - Implement `process_document_upload()` as a FastAPI `BackgroundTasks` function
    - Orchestrate the flow: update status `pending` → `extracting` → `synthesizing` → `done`/`failed`
    - Call `extract_document()` for each file, then `synthesize_l1_facts()` with combined text
    - Handle partial failures (some files fail extraction, proceed with successful ones)
    - _Requirements: 3.11, 4.1, 4.4, 9.4_

  - [x] 6.2 Implement proposal creation and Skip Review mode
    - When `skip_review=false`: create one `PendingProfileChange` entry per proposal, tagged with `source_type="document_upload"` and `session_id=job_id`
    - When `skip_review=true`: write proposals directly to L1 memory without creating pending changes
    - Store proposals on the `Upload_Job` record and update `proposal_count`
    - _Requirements: 5.1, 5.4, 5.7, 5.8_

  - [x] 6.3 Implement the retry-analysis endpoint
    - Implement `POST /api/documents/jobs/{job_id}/retry-analysis` that re-runs synthesis using preserved `extracted_text` from the job record
    - Validate that the job is in `failed` state and `extracted_text` is available
    - Kick off a new background task for synthesis only (skip extraction)
    - _Requirements: 9.5, 9.6_

  - [x] 6.4 Write property test for proposal-to-PendingProfileChange mapping (Property 13)
    - **Property 13: Proposal-to-PendingProfileChange mapping with source tagging**
    - Generate random valid proposal sets with job metadata
    - Assert: one PendingProfileChange per proposal when skip_review=false, all tagged with source_type and session_id; no pending changes when skip_review=true
    - **Validates: Requirements 5.1, 5.4, 5.7**

- [x] 7. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement frontend upload component
  - [x] 8.1 Create the `ChatDocumentUploader` component
    - Render an attachment button within the chat input bar
    - On click, open a native file picker configured to accept all Supported_Formats MIME types
    - Accept up to 5 files per selection; if more than 5 are selected, keep first 5 and show inline warning
    - _Requirements: 1.1, 1.2, 1.3, 1.8_

  - [x] 8.2 Implement file preview chips with validation
    - Display each selected file as a preview chip showing: truncated filename (30 chars + ellipsis), formatted file size (KB or MB), and a remove button
    - Show inline error on chips for files exceeding 10 MB (stating max size)
    - Show inline error on chips for files with unsupported MIME types (listing supported formats)
    - When all files are invalid and no text is present, disable the submit button
    - When user removes all files, hide the file preview area and revert to default state
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.9, 1.10_

  - [x] 8.3 Implement the Skip Review toggle and upload submission
    - Add a "Skip Review" toggle to the upload area (session-scoped, defaults to review-enabled)
    - On submit, upload only valid files + skip_review flag + optional message text via `POST /api/documents/upload`
    - Persist skip-review preference for session duration only; reset on new session
    - _Requirements: 5.7, 5.9, 1.5_

  - [x] 8.4 Write property tests for client-side validation (Properties 1, 2)
    - **Property 1: Client-side file validation partition** — random files with various names/sizes/MIME types, assert correct partition into valid/invalid sets (union = original, intersection = empty)
    - **Property 2: Filename truncation and size formatting** — random strings (0–500 chars), random sizes (0–100MB), assert truncation ≤ 33 chars and size formatting matches expected unit
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7, 1.8**

- [x] 9. Implement frontend status polling and proposal display
  - [x] 9.1 Create the `UploadStatusIndicator` component
    - Poll `GET /api/documents/jobs/{jobId}/status` every 2 seconds while job is in non-terminal state
    - Display animated spinner with stage-appropriate labels: "Uploading files..." (pending), "Reading documents..." (extracting), "Analyzing content..." (synthesizing)
    - Stop polling when job reaches `done` or `failed`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.10_

  - [x] 9.2 Create the `DocumentProposalCard` component
    - When job is `done` with proposals, display an interactive card with each proposal showing field name, proposed value, and source filename
    - Provide individual accept/dismiss controls per proposal
    - Provide an "Apply All" button for batch acceptance
    - When all proposals are resolved, replace interactive controls with a read-only summary (count of accepted/dismissed)
    - When `skip_review=true`, display applied changes as informational read-only summary
    - _Requirements: 5.2, 5.3, 5.5, 5.6, 6.5, 6.9_

  - [x] 9.3 Implement error display and retry functionality
    - When job is `done` with no proposals, display informational message
    - When job is `failed`, display per-file failure reasons and a "Retry" button for failed files
    - When job is `done` with proposals AND failed files, display both proposals and failure list in same card
    - Implement network failure handling: error message + "Retry" button (re-uses selected files); disable after 3 consecutive failures
    - Implement "Retry Analysis" button that calls `POST /api/documents/jobs/{jobId}/retry-analysis`
    - _Requirements: 6.6, 6.7, 6.8, 9.1, 9.2, 9.6_

  - [x] 9.4 Implement style note replacement flow in the UI
    - When a style_note proposal arrives and user already has 5 style notes, display the proposed note alongside existing 5 notes
    - Inform the user max has been reached; allow them to dismiss the proposal or select an existing note to replace
    - If user dismisses, leave existing notes unchanged
    - _Requirements: 7.3, 7.4_

- [x] 10. Integration wiring and final verification
  - [x] 10.1 Register the documents router in the FastAPI app
    - Import and include `documents_router` in the main app
    - Ensure the `/api/documents/` namespace is registered and accessible
    - Verify no route conflicts with existing `/api/ingest/` namespace
    - _Requirements: 8.2_

  - [x] 10.2 Wire frontend upload flow to backend
    - Connect `ChatDocumentUploader` submit action to `POST /api/documents/upload`
    - Connect `UploadStatusIndicator` polling to `GET /api/documents/jobs/{jobId}/status`
    - Connect proposal accept/dismiss actions to existing `POST /api/profile/pending-changes/{field}/(accept|dismiss)` endpoints
    - Ensure chat session remains fully functional during upload processing
    - _Requirements: 5.3, 6.1, 9.3_

  - [x] 10.3 Write integration tests for end-to-end upload flow
    - Test full flow: file upload → extraction → synthesis → proposals displayed → accept/dismiss
    - Test pipeline independence: document pipeline operates while ingestion pipeline is unavailable
    - Test TTL cleanup: files and job records expire after 24 hours
    - Test that document-sourced proposals work with existing accept/dismiss paths
    - _Requirements: 8.1, 8.5, 2.7_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python (FastAPI) and the frontend uses TypeScript (React)
- The `hypothesis` library is already available for property-based tests
- The pipeline is fully independent from the existing `IngestionService` — no shared imports, state, queues, or collections

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.1", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.6", "8.1"] },
    { "id": 3, "tasks": ["2.4", "3.7", "5.1", "8.2"] },
    { "id": 4, "tasks": ["5.2", "5.3", "8.3"] },
    { "id": 5, "tasks": ["5.4", "6.1", "8.4"] },
    { "id": 6, "tasks": ["6.2", "6.3"] },
    { "id": 7, "tasks": ["6.4", "9.1", "9.2"] },
    { "id": 8, "tasks": ["9.3", "9.4", "10.1"] },
    { "id": 9, "tasks": ["10.2"] },
    { "id": 10, "tasks": ["10.3"] }
  ]
}
```
