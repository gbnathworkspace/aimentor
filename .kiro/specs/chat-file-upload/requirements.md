# Requirements Document

## Introduction

This feature extends MentorMan's file upload capability from onboarding-only to active chat sessions. Users can upload PDF (resume) and CSV (LeetCode export) files during a live mentoring session at `/session/[id]`. Uploaded files are processed through the existing ingestion pipeline and their content is made available as context in the current conversation — either updating the user's profile/skill graph (structured path) or providing immediate conversational context (narrative path).

## Glossary

- **Chat_Upload_UI**: The file upload interface component embedded in the chat input area of the session view at `/session/[id]`.
- **Session_Upload_Handler**: The backend endpoint that receives file uploads during an active session, validates them, and initiates ingestion with session-context metadata.
- **Ingestion_Pipeline**: The existing backend service that extracts, routes, and stores user data from file uploads into MongoDB and Atlas Vector Search.
- **Session_Context_Injector**: The component that makes newly ingested file content available to the current session's LLM context assembly without waiting for the full ingestion pipeline to complete embedding.
- **Context_Assembler**: The existing component that assembles LLM context (system prompt + Core Profile + Skill Graph + Episodic RAG + conversation window) fresh on every call.
- **File_Upload_Handler**: The existing component that validates file type/size, stores to S3, and creates Job Records.
- **Job_Record**: A MongoDB document tracking the status of an asynchronous ingestion job (`pending`, `processing`, `done`, `partial`, `failed`).
- **Extracted_Content**: The raw text content extracted from an uploaded file by the PDF_Extractor or CSV_Extractor before routing.
- **Immediate_Context**: A temporary representation of extracted file content that is injected into the current session's LLM context while full ingestion (embedding, structured parsing) proceeds asynchronously.
- **Upload_Message**: A system-generated chat message that represents the file upload event in the conversation timeline, showing upload status and a summary of extracted content.

## Requirements

### Requirement 1: Chat Upload UI Component

**User Story:** As a user in a live mentoring session, I want to upload a PDF or CSV file from the chat input area so that I can share new data with my mentor without leaving the conversation.

#### Acceptance Criteria

1. THE Chat_Upload_UI SHALL render a file attachment button (icon) within the chat input bar at `/session/[id]`
2. WHEN the user clicks the attachment button, THE Chat_Upload_UI SHALL open a native file picker filtered to accept `.pdf` and `.csv` file types
3. WHEN the user selects a file, THE Chat_Upload_UI SHALL display the selected filename (truncated to 30 characters with ellipsis if longer) and file size (formatted as KB for files under 1 MB or MB with one decimal place for files 1 MB and over) in a preview chip within the input area before submission
4. WHEN the user submits the message (with or without accompanying text), THE Chat_Upload_UI SHALL upload the file and any accompanying message text to the Session_Upload_Handler
5. WHILE a file upload is in progress, THE Chat_Upload_UI SHALL display an indeterminate progress indicator on the upload message in the conversation timeline and SHALL disable the attachment button to prevent concurrent uploads
6. WHEN the upload completes successfully, THE Chat_Upload_UI SHALL display an Upload_Message in the conversation timeline showing the filename, file type icon, and a status badge reflecting the processing state (one of: pending, done, partial, or failed)
7. IF the user selects a file with an unsupported type (not `.pdf` or `.csv`), THEN THE Chat_Upload_UI SHALL display an inline error message stating the supported file types and SHALL NOT send the file to the backend
8. IF the user selects a file exceeding 10 MB, THEN THE Chat_Upload_UI SHALL display an inline error message stating the maximum allowed size and SHALL NOT send the file to the backend
9. IF the file upload fails due to a network error or a non-success response from the Session_Upload_Handler, THEN THE Chat_Upload_UI SHALL display an inline error message indicating the upload could not be completed and SHALL allow the user to retry the upload without re-selecting the file
10. THE Chat_Upload_UI SHALL allow the user to remove a selected file from the preview chip before submission by clicking a dismiss control on the chip
11. THE Chat_Upload_UI SHALL accept a maximum of 1 file per message submission
12. WHILE the processing state of an uploaded file is "pending", THE Chat_Upload_UI SHALL poll the job status endpoint at an interval of 3 seconds and update the status badge when the state changes to "done", "partial", or "failed"

### Requirement 2: Session Upload Endpoint

**User Story:** As the system, I want to receive file uploads during an active session so that I can initiate ingestion with the session context metadata attached.

#### Acceptance Criteria

1. WHEN a file upload request is received at `POST /api/session/{sessionId}/upload`, THE Session_Upload_Handler SHALL validate that the session exists and belongs to the authenticated user
2. IF the session does not exist or does not belong to the authenticated user, THEN THE Session_Upload_Handler SHALL return an HTTP 403 response
3. IF the session is not in an active state (session has been ended), THEN THE Session_Upload_Handler SHALL return an HTTP 400 response with a message indicating that uploads are not permitted on inactive sessions
4. WHEN validation passes, THE Session_Upload_Handler SHALL delegate file validation (type, size) to the existing File_Upload_Handler and return any validation errors as an HTTP 400 response to the client
5. WHEN file validation passes, THE Session_Upload_Handler SHALL create a Job_Record with additional metadata fields: `sessionId`, `uploadContext` set to "session", and `accompanyingMessage` containing any user-provided text truncated to a maximum of 2000 characters
6. WHEN the Job_Record is created, THE Session_Upload_Handler SHALL return an HTTP 202 response containing the `jobId` and enqueue the file for asynchronous extraction
7. THE Session_Upload_Handler SHALL tag all ingestion artifacts (S3 path, Job_Record, chunks, embeddings) with `source_context: "session"` and `sessionId` to distinguish session uploads from onboarding uploads
8. IF the `accompanyingMessage` field is not provided in the upload request, THEN THE Session_Upload_Handler SHALL create the Job_Record with `accompanyingMessage` set to an empty string

### Requirement 3: Immediate Context Extraction

**User Story:** As a user, I want the content of my uploaded file to be available in the current conversation quickly so that the mentor can reference it without waiting for full ingestion to complete.

#### Acceptance Criteria

1. WHEN extraction completes for a session-uploaded file, THE Session_Context_Injector SHALL store the Extracted_Content as an Immediate_Context document in MongoDB, associated with the `sessionId`, `userId`, source filename, and upload timestamp
2. WHEN extraction completes for a session-uploaded file, THE Session_Context_Injector SHALL make the Immediate_Context available within 5 seconds of extraction completion, without waiting for the embedding or structured parsing paths to finish
3. WHEN the Immediate_Context is stored, THE Session_Context_Injector SHALL update the Job_Record status to indicate that extracted content is ready for context assembly
4. THE Session_Context_Injector SHALL store the Immediate_Context with a MongoDB TTL index of 24 hours from creation time — after expiry, the full embeddings in Atlas_Vector_Search serve as the permanent retrieval source
5. IF the extracted content exceeds 4000 tokens (measured by the same tokenizer used for LLM context budgeting), THEN THE Session_Context_Injector SHALL truncate the Immediate_Context to the first 4000 tokens, splitting only at sentence boundaries so that no sentence is partially included
6. WHEN a CSV file is extracted, THE Session_Context_Injector SHALL store a human-readable summary listing each topic with its solved count per difficulty level (easy, medium, hard) and total, as the Immediate_Context instead of the raw CSV rows
7. IF the MongoDB write for the Immediate_Context document fails, THEN THE Session_Context_Injector SHALL retry the write once, and if the retry also fails, SHALL mark the Job_Record status as `failed` with an error indicating that immediate context storage was unsuccessful

### Requirement 4: Context Assembly Integration

**User Story:** As a user, I want the mentor to reference my uploaded file content in subsequent responses so that the conversation is informed by the new data.

#### Acceptance Criteria

1. WHEN assembling context for an LLM call in a session that has an active Immediate_Context, THE Context_Assembler SHALL include the Immediate_Context as an additional context block between the Skill Graph nodes and the Episodic RAG results
2. THE Context_Assembler SHALL label each Immediate_Context block with the source filename and upload timestamp so the LLM can reference the file by name in its response
3. WHEN multiple files have been uploaded in the same session, THE Context_Assembler SHALL include all active Immediate_Context documents for that session, ordered by upload timestamp (oldest first)
4. IF the combined Immediate_Context blocks plus existing context exceed the configured token budget for the LLM call, THEN THE Context_Assembler SHALL prioritize Core Profile and Skill Graph over Immediate_Context, dropping Immediate_Context blocks one at a time starting from the oldest upload until the total fits within budget
5. WHEN the full ingestion pipeline completes (job status reaches `done`) for a file, THE Context_Assembler SHALL mark that file's Immediate_Context as inactive and SHALL retrieve the file content exclusively through normal Episodic RAG (vector search), ensuring the same content is not served from both Immediate_Context and Episodic RAG simultaneously
6. WHILE a session has at least one active Immediate_Context document, THE Context_Assembler SHALL include a system instruction informing the LLM that file content has been uploaded mid-session, listing each active file's filename and the user's accompanying message if one was provided
7. WHEN the last active Immediate_Context in a session becomes inactive (due to ingestion completion or TTL expiry), THE Context_Assembler SHALL stop including the mid-session upload system instruction in subsequent LLM calls

### Requirement 5: Ingestion Pipeline Reuse

**User Story:** As a system operator, I want session file uploads to reuse the existing ingestion pipeline so that file processing logic is not duplicated.

#### Acceptance Criteria

1. WHEN a session-uploaded file passes validation, THE Ingestion_Pipeline SHALL process the file through the same Extractor_Service, Ingestion_Router, Structured_Parser, Chunker_Service, and Embedder_Service components used for onboarding uploads
2. WHEN a session-uploaded PDF is processed through the structured path, THE Structured_Parser SHALL merge new structured facts with existing Core_Profile values by overwriting only those fields (`currentRole`, `yearsOfExperience`, `education`, `skills`) for which the new upload provides a non-null extracted value, preserving existing values for any fields where the new upload yields null or no recognizable content
3. WHEN a session-uploaded CSV is processed through the structured path, THE Structured_Parser SHALL merge new LeetCode aggregates with existing Skill_Graph signals by summing solved counts per topic per difficulty level, and SHALL create a new Skill_Graph topic document for any topic present in the new CSV that does not already exist
4. WHEN chunks are generated from a session-uploaded file, THE Chunker_Service SHALL attach additional metadata: `sessionId` and `upload_context: "session"` to each chunk, in addition to the standard metadata fields (`userId`, `source`, `section`, `chunkIndex`, `topic`)
5. THE Ingestion_Pipeline SHALL process session uploads in FIFO order within the same job queue as onboarding uploads — session uploads do not bypass, receive priority over, or get deprioritized relative to queued onboarding jobs
6. WHEN a session-uploaded file has the same source category (resume or leetcode) as a previously ingested onboarding upload, THE Ingestion_Pipeline SHALL follow the re-ingestion handling from Requirement 13 of the ingestion pipeline spec, deleting prior onboarding-source chunks and structured facts for that category before storing new values, while preserving all data tagged with `source_context: "session"` from other session uploads
7. WHEN a session-uploaded file has the same source category as a previously ingested session upload, THE Ingestion_Pipeline SHALL replace the prior session-upload data for that category (deleting old session-source chunks and structured facts for that source category) and store the newly generated values, without affecting onboarding-source data or session-source data from other source categories

### Requirement 6: Upload Status and User Feedback

**User Story:** As a user, I want clear feedback about the processing status of my uploaded file so that I know when it has been incorporated into the conversation.

#### Acceptance Criteria

1. WHEN the job status transitions to `processing`, THE Chat_Upload_UI SHALL update the Upload_Message status badge to "Processing"
2. WHEN the Immediate_Context becomes available (extraction complete), THE Chat_Upload_UI SHALL update the Upload_Message status badge to "Ready" and display a summary of what was extracted, limited to 80 characters maximum (e.g., "Resume: 3 sections extracted" or "LeetCode: 45 problems across 8 topics"), with the summary text sourced from the job status endpoint response
3. WHEN the full ingestion pipeline completes (job status `done`), THE Chat_Upload_UI SHALL update the Upload_Message status badge to "Ingested" indicating that the content is now permanently stored
4. WHEN the job status reaches `partial`, THE Chat_Upload_UI SHALL update the status badge to "Partial" and display a message explaining that structured data was saved but embedding failed
5. IF the job status reaches `failed`, THEN THE Chat_Upload_UI SHALL update the status badge to "Failed" and display the user-facing error message from the Job_Record
6. WHEN the Session_Upload_Handler returns a jobId, THE Chat_Upload_UI SHALL poll the job status endpoint at 2-second intervals until a terminal state (`done`, `partial`, `failed`) is reached or until 5 minutes (150 polls) have elapsed, then stop polling
7. IF polling reaches the 5-minute maximum without the job reaching a terminal state, THEN THE Chat_Upload_UI SHALL stop polling, display a "Timeout" status badge on the Upload_Message, and display a message indicating that processing is taking longer than expected and the user may continue chatting
8. IF a poll request fails due to a network error, THEN THE Chat_Upload_UI SHALL retry the failed poll up to 3 consecutive times with a 4-second interval before treating the job as unreachable and displaying a "Connection Lost" status with a manual "Refresh Status" button
9. WHEN the status reaches "Ready" (Immediate_Context available), THE Chat_Upload_UI SHALL insert a system message in the conversation informing the user that the file content is now available to the mentor

### Requirement 7: Error Handling and Recovery

**User Story:** As a user, I want graceful handling of upload failures so that my session is not disrupted by a failed upload.

#### Acceptance Criteria

1. IF the network request to upload the file fails, THEN THE Chat_Upload_UI SHALL display an error message on the Upload_Message indicating the upload could not be completed due to a network issue, and SHALL present a "Retry" button that re-initiates the upload using the previously selected file without requiring the user to re-select it, for a maximum of 3 retry attempts
2. IF all 3 retry attempts for a network upload failure are exhausted, THEN THE Chat_Upload_UI SHALL disable the "Retry" button, display a message indicating that the upload could not be completed, and re-enable the attachment button so the user can select and upload the file again manually
3. WHEN the user clicks the "Retry" button on a failed Upload_Message, THE Chat_Upload_UI SHALL reset the Upload_Message status badge to its uploading state and re-initiate the upload request to the Session_Upload_Handler
4. IF the extraction step fails (job status `failed`), THEN THE Session_Context_Injector SHALL NOT create an Immediate_Context document, and THE Chat_Upload_UI SHALL display the failure reason from the Job_Record on the Upload_Message and re-enable the attachment button so the user can select and upload a new file
5. WHILE the ingestion pipeline is processing a session upload, THE session SHALL remain fully functional — the user can continue sending messages and receiving responses, and THE Context_Assembler SHALL continue assembling context using the conversation window, Core Profile, Skill Graph, and Episodic RAG without blocking on the in-progress upload
6. IF the Immediate_Context TTL expires before the full ingestion completes, THEN THE Context_Assembler SHALL fall back to the conversation window (which contains the Upload_Message summary) as the only reference to the uploaded file until embeddings are available
7. IF the user uploads a file and then ends the session before ingestion completes, THEN THE Ingestion_Pipeline SHALL continue processing the file to completion, storing results in the permanent stores (MongoDB and Atlas_Vector_Search) regardless of session state
8. IF the Session_Upload_Handler receives a request while another upload for the same session is still in `pending` or `processing` state, THEN THE Session_Upload_Handler SHALL reject the request with an HTTP 409 response indicating that a previous upload is still being processed
