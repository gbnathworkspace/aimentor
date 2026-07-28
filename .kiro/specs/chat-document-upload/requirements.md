# Requirements Document

## Introduction

MentorMan's chat interface currently supports text-only conversations. Users accumulate knowledge artifacts (resumes, job descriptions, course syllabi, notes, exported data) in various file formats that contain information relevant to their learning profile. Today, the only way to get this information into L1 memory is through onboarding uploads (resume + LeetCode CSV only) or manual editing via the Settings > Memory chat box.

This feature adds document upload directly in the chat interface, supporting a broad set of common formats (CSV, PDF, DOCX, XLSX, JSON, TXT, and others). Uploaded documents are processed through a **new dedicated pipeline** — separate from the existing `IngestionService` used for onboarding — that extracts content, uses an LLM to summarize it into structured L1 facts, and populates the existing L1 memory fields visible in the UI. Multiple files can be uploaded at once.

Key distinctions from existing upload paths:
- **Not the onboarding ingestion pipeline** (`ingestion-pipeline/`) — that handles resume/CSV only, writes to both MongoDB and Vector DB, and is tightly coupled to onboarding flows.
- **Not `session_upload.py`** — that creates ephemeral `immediate_contexts` for session-scoped LLM injection, discarded when the session ends.
- **Not `extraction.py`** — that chunks and embeds for episodic retrieval (L3). Does not touch L1.

This is a new pipeline that reads documents → extracts text → LLM-summarizes into L1-shaped structured facts → presents to user for confirmation → writes to L1 memory via the existing `PendingProfileChange` mechanism.

## Glossary

- **Chat_Document_Uploader**: The UI component in the chat interface that allows users to select and upload one or more documents for L1 memory population.
- **Document_Ingestion_Pipeline**: The new dedicated backend pipeline that receives uploaded documents, extracts their content, and produces structured L1 facts. Separate from the existing `IngestionService`.
- **Document_Extractor**: The component within the Document_Ingestion_Pipeline responsible for reading file content based on format (PDF, DOCX, CSV, XLSX, JSON, TXT).
- **L1_Fact_Synthesizer**: The LLM-powered component that takes extracted document text and produces structured field proposals conforming to L1 memory schema (`ProposableField` values, `focus_areas` suggestions, `learning_context_structured` keys).
- **L1_Memory**: The Core Profile layer (Layer 1 of the memory hierarchy), stored in MongoDB, always injected into every LLM context. Fields include `learning_context`, `learning_context_detail`, `goal_orientation`, `focus_areas`, `style_notes`, and teaching preferences.
- **Pending_Change**: An instance of `PendingProfileChange` — a proposed L1 modification awaiting user accept/dismiss. The existing confirmation mechanism in the profile router.
- **Upload_Job**: A tracked unit of work representing one batch of uploaded files, with status progression from `pending` through `extracting`, `synthesizing`, to `done` or `failed`.
- **Supported_Formats**: The set of accepted file types: PDF, DOCX, CSV, XLSX, JSON, TXT, MD (Markdown), and RTF.

## Requirements

### Requirement 1: Chat Upload Interface

**User Story:** As a user in a chat session, I want to upload documents directly from the chat input area so that I can share knowledge artifacts without leaving the conversation or navigating to settings.

#### Acceptance Criteria

1. THE Chat_Document_Uploader SHALL render an attachment button within the chat input bar at the session view.
2. WHEN the user clicks the attachment button, THE Chat_Document_Uploader SHALL open a native file picker configured to accept all Supported_Formats.
3. WHEN the user selects files, THE Chat_Document_Uploader SHALL accept up to 5 files in a single selection.
4. WHEN files are selected, THE Chat_Document_Uploader SHALL display each selected file as a preview chip showing filename (truncated to 30 characters with ellipsis), file size (KB for files under 1 MB, MB with one decimal for 1 MB and over), and a remove button that, when clicked, removes that file from the selection and removes its preview chip from the display.
5. WHEN the user submits the message (with or without accompanying text), THE Chat_Document_Uploader SHALL upload only the valid selected files (those not flagged with size or format errors) and any accompanying message to the Document_Ingestion_Pipeline endpoint.
6. IF any selected file exceeds 10 MB, THEN THE Chat_Document_Uploader SHALL display an inline error on that file's preview chip stating the maximum allowed size, and SHALL NOT include that file in the upload submission.
7. IF any selected file has an unsupported MIME type, THEN THE Chat_Document_Uploader SHALL display an inline error on that file's preview chip listing the supported formats, and SHALL NOT include that file in the upload submission.
8. IF more than 5 files are selected, THEN THE Chat_Document_Uploader SHALL accept only the first 5 files and display an inline warning indicating the maximum file count.
9. IF all selected files are invalid (all flagged with size or format errors) and no accompanying text is present, THEN THE Chat_Document_Uploader SHALL disable the submit button until the user adds valid files or enters text.
10. WHEN the user removes all files from the selection via the remove button, THE Chat_Document_Uploader SHALL hide the file preview area and revert the chat input bar to its default text-only state.

### Requirement 2: Document Upload Endpoint

**User Story:** As the system, I want a dedicated endpoint for chat-based document uploads so that this pipeline operates independently from the existing ingestion service.

#### Acceptance Criteria

1. WHEN a document upload request is received at `POST /api/documents/upload`, THE Document_Ingestion_Pipeline SHALL validate that the request comes from an authenticated user.
2. IF the user is not authenticated, THEN THE Document_Ingestion_Pipeline SHALL return an HTTP 401 response.
3. WHEN authentication passes, THE Document_Ingestion_Pipeline SHALL validate each file's MIME type against Supported_Formats and size against the 10 MB per-file limit, and SHALL reject any request containing more than 5 files with an HTTP 400 response indicating the maximum batch size.
4. IF any file fails validation but at least one file passes, THEN THE Document_Ingestion_Pipeline SHALL proceed with the valid files, create the Upload_Job, and return an HTTP 202 response that includes the `jobId`, the count of accepted files, and a list of rejected files with their specific validation failure reasons.
5. IF all files in the request fail validation, THEN THE Document_Ingestion_Pipeline SHALL return an HTTP 400 response listing each file and its specific validation failure, and SHALL NOT create an Upload_Job.
6. WHEN all files pass validation, THE Document_Ingestion_Pipeline SHALL create an Upload_Job record in MongoDB with status `pending`, the list of accepted files, user ID, and timestamp, and SHALL return an HTTP 202 response containing the `jobId` and the count of accepted files.
7. THE Document_Ingestion_Pipeline SHALL store raw uploaded files temporarily with a 24-hour TTL for re-processing in case of extraction failures, and SHALL automatically delete stored files after the TTL expires.

### Requirement 3: Multi-Format Document Extraction

**User Story:** As a user, I want to upload documents in the format they already exist in so that I do not need to convert files before uploading.

#### Acceptance Criteria

1. WHEN the uploaded file is PDF, THE Document_Extractor SHALL extract text content and represent paragraph boundaries as double newlines and section headings as lines prefixed with their heading text followed by a newline separator.
2. WHEN the uploaded file is DOCX, THE Document_Extractor SHALL extract text content including headings, paragraphs, and list items while discarding formatting metadata (font, color, spacing).
3. WHEN the uploaded file is CSV, THE Document_Extractor SHALL parse rows up to a maximum of 5000 rows and produce a structured text representation with column headers and row values, discarding rows beyond the limit.
4. WHEN the uploaded file is XLSX, THE Document_Extractor SHALL read the first sheet by default, parse rows up to a maximum of 5000 rows, and produce a structured text representation with column headers and row values, discarding rows beyond the limit.
5. WHEN the uploaded file is JSON, THE Document_Extractor SHALL parse the JSON structure and produce a flattened key-path and value text representation, traversing nested objects up to 10 levels deep and truncating arrays to the first 100 elements.
6. WHEN the uploaded file is TXT or MD, THE Document_Extractor SHALL read the file as UTF-8 text, replacing any invalid byte sequences with the Unicode replacement character (U+FFFD).
7. WHEN the uploaded file is RTF, THE Document_Extractor SHALL strip RTF formatting and extract plain text content.
8. IF extraction produces no usable text (empty content after processing), THEN THE Document_Extractor SHALL mark that file as `failed` in the Upload_Job with an error message indicating the file contained no extractable content.
9. IF extraction fails due to a corrupted or unreadable file, THEN THE Document_Extractor SHALL mark that file as `failed` in the Upload_Job with an error message indicating the file could not be read.
10. IF the uploaded file is password-protected or encrypted, THEN THE Document_Extractor SHALL mark that file as `failed` in the Upload_Job with an error message indicating the file is password-protected and cannot be processed.
11. WHEN multiple files are uploaded in one batch, THE Document_Extractor SHALL process each file independently so that one file's failure does not block extraction of remaining files.
12. WHEN extraction of a file succeeds, THE Document_Extractor SHALL truncate the extracted text output to a maximum of 50,000 characters, cutting at the nearest sentence boundary, before passing it to the L1_Fact_Synthesizer.

### Requirement 4: LLM-Powered L1 Fact Synthesis

**User Story:** As the system, I want to use an LLM to convert extracted document text into structured L1 memory facts so that raw text does not bloat the Core Profile token budget.

#### Acceptance Criteria

1. WHEN extracted text is available from one or more files in an Upload_Job, THE L1_Fact_Synthesizer SHALL set the Upload_Job status to `synthesizing` and send the extracted text to an LLM with a prompt instructing it to produce structured field proposals matching L1 memory schema.
2. WHEN relevant content is found in the extracted text, THE L1_Fact_Synthesizer SHALL produce proposals for the following L1 fields: `goal_orientation` (a valid `GoalOrientation` enum value), `learning_context_structured` key-value pairs, `style_note` entries (each including a `category` from the `StyleNoteCategory` enum, a `note` of at most 140 characters, and a `source_quote`), and `focus_areas` suggestions (each a string of at most 60 characters).
3. WHEN the combined extracted text from all files in the Upload_Job exceeds 8000 tokens (measured by the tokenizer of the target LLM model), THE L1_Fact_Synthesizer SHALL truncate the combined text at a sentence boundary to fit within 8000 tokens, discarding the remainder.
4. WHEN multiple files are in the same Upload_Job, THE L1_Fact_Synthesizer SHALL concatenate all extracted texts and process them together in a single LLM call to produce a unified set of proposals rather than conflicting per-file proposals.
5. THE L1_Fact_Synthesizer SHALL validate proposed `learning_context_structured` keys against `ALLOWED_STRUCTURED_KEYS` for the user's current `learning_context` and discard any keys not in the allowed set.
6. WHEN the L1_Fact_Synthesizer proposes a `style_note`, THE L1_Fact_Synthesizer SHALL include a `source_quote` field containing a verbatim span (at most 200 characters) from the extracted text, not a paraphrase.
7. IF the LLM produces no actionable L1 proposals from the extracted content, THEN THE L1_Fact_Synthesizer SHALL mark the Upload_Job as `done` with a result indicating no memory updates were found, and SHALL inform the user that the document did not contain information relevant to their learning profile.
8. IF the LLM call fails (timeout, rate limit, service error), THEN THE L1_Fact_Synthesizer SHALL retry once after a delay of at least 2 seconds, and if the retry also fails, SHALL mark the Upload_Job as `failed` with an error message indicating the failure reason (timeout, rate limit, or service error).
9. IF the LLM response does not conform to the expected structured output schema (missing required fields, invalid enum values, or malformed JSON), THEN THE L1_Fact_Synthesizer SHALL discard the malformed proposals, log the parsing failure, and mark the Upload_Job as `failed` with an error indicating that synthesis produced an unparseable result.

### Requirement 5: User Confirmation Before L1 Writes

**User Story:** As a user, I want to review what the system extracted from my documents before it changes my learning profile so that bad extractions cannot silently corrupt my memory. Alternatively, I want to skip review and apply all changes directly when I trust the extraction.

#### Acceptance Criteria

1. WHEN the L1_Fact_Synthesizer produces proposals, THE Document_Ingestion_Pipeline SHALL by default create `PendingProfileChange` entries using the existing pending-change mechanism, one entry per proposed field change.
2. WHEN proposals are presented in the chat, THE system SHALL display them as a structured summary showing each proposed change with its field name, proposed value, and the source document filename.
3. WHEN a Pending_Change from a document is accepted, THE system SHALL apply it through the same `accept_pending_change` path used for profiling-agent proposals.
4. WHEN a Pending_Change is created from a document upload, THE system SHALL tag it with a `source_type` of `"document_upload"` and reference the Upload_Job ID in the `session_id` field to distinguish it from session-derived proposals.
5. THE system SHALL allow the user to accept or dismiss each proposed change individually — batch acceptance is optional but individual control is required.
6. THE Chat_Document_Uploader SHALL provide an "Apply All" button on the proposals card that accepts all proposed changes in a single action without requiring individual review.
7. THE Chat_Document_Uploader SHALL provide a "Skip Review" toggle (or equivalent control) at upload time that, when enabled, causes the Document_Ingestion_Pipeline to write all synthesized proposals directly to L1 memory without creating Pending_Changes or waiting for user confirmation.
8. WHEN "Skip Review" is enabled and proposals are written directly, THE system SHALL still display the applied changes in the chat as an informational summary (read-only, not interactive) so the user can see what was written.
9. WHEN "Skip Review" is enabled, THE system SHALL persist the user's preference for the duration of the session but SHALL NOT remember it across sessions — each new session defaults to review-enabled.

### Requirement 6: Upload Status and Chat Feedback

**User Story:** As a user, I want clear feedback in the chat about what is happening with my uploaded documents so that I know the system is processing them and can see the results.

#### Acceptance Criteria

1. WHILE the Document_Ingestion_Pipeline is processing an Upload_Job, THE Chat_Document_Uploader SHALL poll the Upload_Job status endpoint every 2 seconds and display a processing indicator in the chat timeline consisting of an animated spinner and a text label showing the current stage.
2. WHEN the Upload_Job is created with status `pending`, THE system SHALL display the chat status label "Uploading files..."
3. WHEN the Upload_Job transitions to `extracting`, THE system SHALL update the chat status label to "Reading documents..."
4. WHEN the Upload_Job transitions to `synthesizing`, THE system SHALL update the chat status label to "Analyzing content..."
5. WHEN the Upload_Job reaches `done` with proposals, THE system SHALL display the proposed L1 changes in the chat as an interactive card with accept/dismiss controls for each proposal.
6. WHEN the Upload_Job reaches `done` with no proposals, THE system SHALL display a message in the chat indicating that no profile-relevant information was found in the uploaded documents.
7. IF the Upload_Job reaches `failed`, THEN THE system SHALL display an error message in the chat indicating which files failed and the reason for each failure, and SHALL display a "Retry" button that re-initiates the upload for the failed files.
8. IF the Upload_Job reaches `done` with proposals and some files in the batch failed extraction, THEN THE system SHALL display both the proposals from successful files and a list of failed files with their failure reasons in the same chat card.
9. WHEN the user accepts or dismisses proposals from the chat card, THE system SHALL visually mark each proposal as "accepted" or "dismissed" and, once all proposals in the card have been resolved, SHALL replace the interactive controls with a read-only summary showing the count of accepted and dismissed changes.
10. WHEN the Upload_Job reaches a terminal state (`done` or `failed`), THE Chat_Document_Uploader SHALL stop polling the status endpoint.

### Requirement 7: Accumulation Behavior

**User Story:** As a user who uploads different documents over time, I want each upload to add to my profile rather than replace previous uploads so that my L1 memory reflects everything I have shared.

#### Acceptance Criteria

1. WHEN a new document upload produces proposals, THE Document_Ingestion_Pipeline SHALL NOT discard or overwrite L1 field values (`focus_areas`, `style_notes`, `goal_orientation`, `learning_context_structured` keys) derived from previously accepted document uploads — new proposals SHALL be additive to the existing profile state.
2. WHEN the L1_Fact_Synthesizer produces a `focus_areas` suggestion, THE L1_Fact_Synthesizer SHALL compare it against all existing focus areas using case-insensitive exact string matching and SHALL NOT propose a focus area that matches an existing entry; only focus areas with no case-insensitive match in the current list SHALL be proposed.
3. WHEN a new `style_note` is proposed and the user already has 5 style notes (the maximum per `profile.py` schema), THE system SHALL display the proposed note alongside all 5 existing notes in the chat interface and inform the user that the maximum has been reached, prompting the user to either dismiss the new proposal or select one existing note to remove and replace with the proposed note.
4. IF the user dismisses the proposed style note when the maximum has been reached, THEN THE system SHALL discard the proposal and leave the existing 5 style notes unchanged.
5. WHEN a document upload completes (status transitions to `done`, `partial`, or `failed`), THE Document_Ingestion_Pipeline SHALL record the following fields on the Upload_Job record: filename of each uploaded file, `created_at` timestamp, final `status` value, and integer count of proposals generated (0 if extraction failed before synthesis).

### Requirement 8: Pipeline Independence

**User Story:** As a system operator, I want the chat document upload pipeline to be fully independent from the existing ingestion pipeline so that changes to one do not affect the other.

#### Acceptance Criteria

1. THE Document_Ingestion_Pipeline SHALL NOT import from, depend on, or share runtime state with the existing `IngestionService` (the onboarding pipeline in `ingestion-pipeline/`). Shared framework-level utilities (authentication middleware, database connection clients, logging) that are not owned by or located within `ingestion-pipeline/` are permitted.
2. THE Document_Ingestion_Pipeline SHALL have its own endpoint namespace (`/api/documents/`) separate from the existing `/api/ingest/` namespace, with no route handlers registered under `/api/ingest/`.
3. THE Document_Ingestion_Pipeline SHALL NOT write to Vector DB or produce embeddings — its sole output target is L1 memory via `PendingProfileChange` entries written to the profiles collection in MongoDB.
4. THE Document_Ingestion_Pipeline SHALL NOT modify Skill Graph (L2) signals — extracted content maps only to L1 Core Profile fields.
5. IF the existing ingestion pipeline is unavailable or experiencing errors, THEN THE Document_Ingestion_Pipeline SHALL continue to accept uploads, extract content, synthesize proposals, and write `PendingProfileChange` entries with no increase in error rate or response latency attributable to the other pipeline's failure.
6. THE Document_Ingestion_Pipeline SHALL NOT share job queues, upload storage buckets, or Upload_Job collections with the existing `IngestionService` — each pipeline SHALL maintain its own processing state independently.

### Requirement 9: Error Handling and Resilience

**User Story:** As a user, I want document upload failures to be handled gracefully so that my chat session is not disrupted.

#### Acceptance Criteria

1. IF the network request to upload files fails (connection error, HTTP 5xx response, or no response within 30 seconds), THEN THE Chat_Document_Uploader SHALL display an error message indicating the upload could not be completed, along with a "Retry" button that re-initiates the upload using the previously selected files without requiring re-selection.
2. IF a retry is attempted and fails 3 consecutive times, THEN THE Chat_Document_Uploader SHALL disable the retry button and display a message indicating the upload is unavailable and suggesting the user try again later; the retry button SHALL remain disabled until the user refreshes the page or starts a new session.
3. WHILE the Document_Ingestion_Pipeline is processing uploaded files, THE chat session SHALL remain fully functional — the user can continue sending messages, receiving responses, and initiating new uploads without blocking.
4. IF one file in a multi-file batch fails extraction while others succeed, THEN THE Document_Ingestion_Pipeline SHALL continue processing the successful files and report individual file failures to the user indicating the failed filename and the reason for failure (e.g., no extractable content or unreadable file).
5. IF the LLM synthesis step fails after successful extraction, THEN THE Document_Ingestion_Pipeline SHALL preserve the extracted text in the Upload_Job record for 24 hours so that synthesis can be retried without re-uploading.
6. IF the LLM synthesis step has failed and extracted text is preserved in the Upload_Job record, THEN THE system SHALL provide a "Retry Analysis" button in the chat that triggers a new synthesis attempt using the preserved extracted text without requiring re-upload or re-extraction.

## Out of Scope

- Writing to Vector DB (L3 episodic memory) — this pipeline targets L1 only.
- Writing to Skill Graph (L2) — no skill signals are derived from these uploads.
- Editing or deleting previously uploaded documents.
- Re-running extraction on an already-processed document.
- Image/OCR processing — only text-based document formats are supported.
- Any modification to the existing onboarding ingestion pipeline.
- Real-time streaming of extraction progress (status polling is sufficient).
