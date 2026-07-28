# Design Document: Chat Document Upload

## Overview

This design implements a chat-based document upload feature for MentorMan that allows users to upload knowledge artifacts (resumes, job descriptions, course syllabi, notes, exported data) directly from the chat interface. The pipeline processes uploaded documents through multi-format text extraction, LLM-powered fact synthesis, and the existing `PendingProfileChange` mechanism to populate L1 memory fields.

The system is intentionally decoupled from:
- The onboarding `IngestionService` (which handles resume/CSV → MongoDB + Vector DB)
- `session_upload.py` (which creates ephemeral `immediate_contexts`)
- `extraction.py` (which chunks and embeds for L3 episodic retrieval)

This pipeline's sole output target is L1 Core Profile via `PendingProfileChange` entries.

### Key Design Decisions

| Decision | Rationale |
|---|---|
| New dedicated pipeline (not extending IngestionService) | Avoids coupling to onboarding flows; different output targets (L1 only vs L1+L2+L3); different file format support |
| Single LLM call for all files in a batch | Produces unified, non-conflicting proposals; reduces cost; avoids duplicate/contradictory per-file proposals |
| Reuse existing `PendingProfileChange` mechanism | Users already understand accept/dismiss; no new confirmation UX to learn; same code path guarantees L1 schema compliance |
| Async processing with status polling | Extraction + LLM synthesis can take 5–15s; polling every 2s keeps the chat responsive without WebSocket complexity |
| 24-hour TTL for stored files | Allows synthesis retry without re-upload; auto-cleanup prevents unbounded storage growth |
| Skip Review option (session-scoped) | Power users who trust the extraction can opt out of per-field confirmation; defaults to review-enabled each session for safety |

---

## Architecture

```mermaid
flowchart TB
    subgraph Frontend ["React Frontend (mentorman-web)"]
        A[ChatUploadButton] --> B[File Preview Chips]
        B --> C[Upload Submit]
        C --> D[POST /api/documents/upload]
        D --> E[Poll GET /api/documents/jobs/:jobId/status]
        E --> F[ProposalCard - accept/dismiss]
    end

    subgraph Backend ["Unified Backend (FastAPI)"]
        G[documents_router.py] --> H[File Validation]
        H --> I[Store to local uploads/ with 24h TTL]
        I --> J[Create Upload_Job record]
        J --> K[Background Task: DocumentPipeline]
        
        subgraph Pipeline ["Document Ingestion Pipeline"]
            K --> L[Document Extractor]
            L --> M{All files extracted?}
            M -->|Yes| N[L1 Fact Synthesizer]
            M -->|Partial| N
            N --> O{Proposals generated?}
            O -->|Yes| P[Create PendingProfileChange entries]
            O -->|No| Q[Mark job done - no proposals]
            P --> R[Mark job done with proposals]
        end
    end

    subgraph Storage ["Data Layer"]
        S[(MongoDB: document_upload_jobs)]
        T[(MongoDB: profiles.pending_changes)]
        U[(Local disk: uploads/{userId}/{jobId}/)]
    end

    J --> S
    P --> T
    I --> U
```

### Data Flow

1. **User selects files** → Client validates format/size → Shows preview chips
2. **User submits** → `POST /api/documents/upload` (multipart/form-data)
3. **Server validates** → Stores files → Creates `Upload_Job` → Returns `jobId` (HTTP 202)
4. **Background task starts** → Status: `pending` → `extracting` → `synthesizing` → `done`/`failed`
5. **Client polls** → Every 2s via `GET /api/documents/jobs/{jobId}/status`
6. **On done** → Client displays proposals as interactive card
7. **User accepts/dismisses** → Existing `POST /api/profile/pending-changes/{field}/(accept|dismiss)`

---

## Components and Interfaces

### Frontend Components

#### `ChatDocumentUploader` (enhanced from existing `ChatUploadButton`)

The existing `ChatUploadButton` component currently supports single-file (PDF/CSV) upload for onboarding. This will be extended into a multi-file uploader supporting all `Supported_Formats`.

```typescript
// New props interface
interface ChatDocumentUploaderProps {
  sessionId: string;
  disabled: boolean;
  onFilesSubmitted: (files: File[], skipReview: boolean, message?: string) => void;
}

// Supported MIME types
const SUPPORTED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // DOCX
  'text/csv',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // XLSX
  'application/json',
  'text/plain',
  'text/markdown',
  'application/rtf',
] as const;

const MAX_FILES = 5;
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
```

#### `DocumentProposalCard`

A new chat message component that renders synthesized L1 proposals with accept/dismiss controls.

```typescript
interface DocumentProposalCardProps {
  jobId: string;
  proposals: Proposal[];
  failedFiles?: FailedFile[];
  onAccept: (proposalId: string) => void;
  onDismiss: (proposalId: string) => void;
  onAcceptAll: () => void;
}

interface Proposal {
  id: string;
  field: ProposableField;
  proposedValue: Record<string, unknown>;
  reason: string;
  sourceFilename: string;
  status: 'pending' | 'accepted' | 'dismissed';
}
```

#### `UploadStatusIndicator`

Displays processing state in the chat timeline with animated spinner and stage labels.

```typescript
interface UploadStatusIndicatorProps {
  jobId: string;
  status: 'pending' | 'extracting' | 'synthesizing';
  label: string; // "Uploading files..." | "Reading documents..." | "Analyzing content..."
}
```

### Backend Components

#### `documents_router.py` — Route Handler

New router at `/api/documents/` namespace, fully independent from `/api/ingest/`.

```python
# app/routers/documents.py
router = APIRouter(prefix="/api/documents", tags=["Documents"])

@router.post("/upload", status_code=202)
async def upload_documents(
    files: list[UploadFile],
    skip_review: bool = Form(default=False),
    message: Optional[str] = Form(default=None),
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_auth),
) -> UploadResponse:
    """Accept document upload, validate, store, create job, return jobId."""
    ...

@router.get("/jobs/{job_id}/status")
async def get_job_status(
    job_id: str,
    user_id: str = Depends(require_auth),
) -> JobStatusResponse:
    """Return current Upload_Job status for polling."""
    ...

@router.post("/jobs/{job_id}/retry-analysis")
async def retry_analysis(
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_auth),
) -> dict:
    """Retry LLM synthesis using preserved extracted text."""
    ...
```

#### `document_extractor.py` — Multi-Format Extraction

```python
# app/services/document_extractor.py

class ExtractionResult:
    filename: str
    text: str           # Extracted text, max 50,000 chars
    success: bool
    error: Optional[str]

async def extract_document(filepath: str, mime_type: str) -> ExtractionResult:
    """Route to appropriate extractor based on MIME type."""
    ...

# Individual extractors
async def extract_pdf(filepath: str) -> str: ...
async def extract_docx(filepath: str) -> str: ...
async def extract_csv(filepath: str) -> str: ...
async def extract_xlsx(filepath: str) -> str: ...
async def extract_json(filepath: str) -> str: ...
async def extract_text(filepath: str) -> str: ...   # TXT and MD
async def extract_rtf(filepath: str) -> str: ...
```

#### `l1_fact_synthesizer.py` — LLM Synthesis

```python
# app/services/l1_fact_synthesizer.py

class SynthesisResult:
    proposals: list[dict]   # Validated PendingProfileChange-shaped dicts
    success: bool
    error: Optional[str]

async def synthesize_l1_facts(
    extracted_text: str,
    user_id: str,
    job_id: str,
    learning_context: LearningContext,
) -> SynthesisResult:
    """Send extracted text to LLM, validate proposals against L1 schema."""
    ...
```

#### `document_pipeline.py` — Orchestrator

```python
# app/services/document_pipeline.py

async def process_document_upload(
    job_id: str,
    user_id: str,
    file_paths: list[str],
    mime_types: list[str],
    skip_review: bool,
) -> None:
    """Background task: extract → synthesize → create pending changes."""
    ...
```

### API Contracts

#### `POST /api/documents/upload`

**Request:** `multipart/form-data`
- `files`: Up to 5 files (max 10 MB each)
- `skip_review`: boolean (default: false)
- `message`: optional string (accompanying chat message)

**Response (202):**
```json
{
  "jobId": "uuid",
  "acceptedFiles": 3,
  "rejectedFiles": [
    { "filename": "large.pdf", "reason": "File exceeds 10 MB limit" }
  ]
}
```

**Error (400):** All files invalid
```json
{
  "detail": {
    "message": "All files failed validation",
    "errors": [
      { "filename": "x.exe", "reason": "Unsupported file format" }
    ]
  }
}
```

**Error (401):** Not authenticated

#### `GET /api/documents/jobs/{jobId}/status`

**Response:**
```json
{
  "jobId": "uuid",
  "status": "synthesizing",
  "files": [
    { "filename": "resume.pdf", "status": "extracted" },
    { "filename": "notes.docx", "status": "extracting" }
  ],
  "proposals": null,
  "failedFiles": [],
  "createdAt": "2026-07-23T10:00:00Z"
}
```

When `status` is `done` with proposals:
```json
{
  "jobId": "uuid",
  "status": "done",
  "proposals": [
    {
      "field": "style_note",
      "proposedValue": { "category": "motivation", "note": "Responds well to real-world examples" },
      "reason": "Multiple references to preferring practical examples over theory",
      "sourceFilename": "learning_preferences.pdf"
    }
  ],
  "failedFiles": [
    { "filename": "corrupted.xlsx", "reason": "File could not be read" }
  ],
  "proposalCount": 3,
  "createdAt": "2026-07-23T10:00:00Z"
}
```

---

## Data Models

### `Upload_Job` (MongoDB: `document_upload_jobs` collection)

```python
class DocumentUploadJob(BaseModel):
    job_id: str                          # UUID
    user_id: str
    status: Literal["pending", "extracting", "synthesizing", "done", "failed"]
    files: list[UploadFileRecord]
    skip_review: bool = False
    message: Optional[str] = None        # Accompanying chat message
    
    # Extraction results (preserved for retry)
    extracted_text: Optional[str] = None  # Combined text from all files
    
    # Synthesis results
    proposals: Optional[list[dict]] = None
    proposal_count: int = 0
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    expires_at: datetime                  # created_at + 24 hours (TTL)

class UploadFileRecord(BaseModel):
    filename: str
    mime_type: str
    file_path: str                        # Local storage path
    size_bytes: int
    status: Literal["pending", "extracted", "failed"]
    error: Optional[str] = None
```

### Extended `PendingProfileChange` (tagging)

Document-sourced proposals use the existing `PendingProfileChange` model with:
- `session_id` field stores the `job_id` (for traceability)
- A new `source_type` field distinguishes document uploads from session-derived proposals

```python
# Extension to existing PendingProfileChange usage
# When creating from document upload:
PendingProfileChange(
    field=ProposableField.STYLE_NOTE,
    proposed_value={"category": "communication", "note": "...", "source_quote": "..."},
    reason="Extracted from resume.pdf",
    session_id=job_id,          # Upload_Job ID for traceability
    created_at=datetime.now(timezone.utc),
)
# source_type="document_upload" added to the dict representation
```

### LLM Synthesis Prompt Output Schema

```python
class L1SynthesisOutput(BaseModel):
    """Expected structured output from the LLM synthesis call."""
    goal_orientation: Optional[GoalOrientation] = None
    learning_context_structured: Optional[dict[str, str]] = None
    style_notes: Optional[list[SynthesizedStyleNote]] = None
    focus_areas: Optional[list[str]] = None

class SynthesizedStyleNote(BaseModel):
    category: StyleNoteCategory
    note: str = Field(max_length=140)
    source_quote: str = Field(max_length=200)  # Verbatim from extracted text
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Client-side file validation correctly partitions files

*For any* set of files with random names, sizes, and MIME types, the validation function SHALL partition them into a valid set (size ≤ 10 MB, MIME type in Supported_Formats, count ≤ 5) and an invalid set, where the union of both sets equals the original input and the intersection is empty.

**Validates: Requirements 1.3, 1.5, 1.6, 1.7, 1.8**

### Property 2: Filename truncation and size formatting are deterministic and reversible-in-meaning

*For any* filename string, `truncateFilename` SHALL return a string of at most 33 characters (30 + "...") that starts with the same prefix as the original. *For any* file size in bytes, `formatFileSize` SHALL return a string in KB (for sizes < 1 MB) or MB with one decimal (for sizes ≥ 1 MB), and the numeric value SHALL be mathematically equivalent to the input size converted to the displayed unit.

**Validates: Requirements 1.4**

### Property 3: Server-side batch validation accepts valid subset and rejects invalid

*For any* upload request containing a list of files with random sizes, MIME types, and count, the endpoint SHALL: (a) reject the entire request with 400 if count > 5, (b) return 400 if all files fail individual validation, (c) return 202 with the correct `acceptedFiles` count and `rejectedFiles` list if at least one file passes validation.

**Validates: Requirements 2.3, 2.4, 2.5, 2.6**

### Property 4: Tabular extraction respects row limits

*For any* CSV or XLSX input with N rows (N ≥ 0), the extractor SHALL produce output containing at most 5000 data rows. When N > 5000, the output SHALL contain exactly 5000 rows. When N ≤ 5000, the output SHALL contain exactly N rows. Column headers SHALL always be preserved in the output.

**Validates: Requirements 3.3, 3.4**

### Property 5: JSON flattening respects depth and array limits

*For any* valid JSON object, the flattening function SHALL: (a) traverse nested objects to at most 10 levels deep, ignoring deeper content; (b) truncate arrays to at most 100 elements; (c) produce key-path representations where each key-path correctly identifies the location of its corresponding value in the original structure up to the depth limit.

**Validates: Requirements 3.5**

### Property 6: UTF-8 text extraction replaces invalid bytes

*For any* byte sequence, the text extractor SHALL produce a valid UTF-8 string where every invalid byte sequence in the input is replaced by exactly one U+FFFD character, and all valid UTF-8 subsequences are preserved unchanged.

**Validates: Requirements 3.6**

### Property 7: RTF extraction preserves text content

*For any* plain text string wrapped in valid RTF formatting, the RTF extractor SHALL produce output that contains the original plain text content with all RTF control words and formatting markers removed.

**Validates: Requirements 3.7**

### Property 8: Independent file processing — one failure does not block others

*For any* batch of files where some files are valid and extractable and others are corrupted/empty, the pipeline SHALL produce extraction results for all valid files regardless of how many other files in the batch fail. The count of successful extractions SHALL equal the count of valid files in the input.

**Validates: Requirements 3.11, 9.4**

### Property 9: Text truncation respects character limit at sentence boundary

*For any* extracted text exceeding 50,000 characters, the truncation function SHALL produce output that: (a) is at most 50,000 characters long; (b) ends at a sentence boundary (period, question mark, or exclamation mark followed by whitespace or end-of-string); (c) is a prefix of the original text (no content reordering).

**Validates: Requirements 3.12**

### Property 10: Token-based truncation respects token limit at sentence boundary

*For any* combined text exceeding 8000 tokens, the truncation function SHALL produce output that: (a) fits within 8000 tokens as measured by the target LLM tokenizer; (b) ends at a sentence boundary; (c) is a prefix of the original text.

**Validates: Requirements 4.3**

### Property 11: LLM output schema validation accepts only well-formed proposals

*For any* JSON object representing an LLM synthesis response, the validator SHALL: (a) accept it only if all required fields are present with valid enum values and correct types; (b) reject it if any field has an invalid enum value, is missing a required sub-field, or has an incorrect type; (c) for style_note proposals, require a non-empty `source_quote` of at most 200 characters.

**Validates: Requirements 4.2, 4.6, 4.9**

### Property 12: Allowed structured keys validation

*For any* proposed `learning_context_structured` key-value pair and any `LearningContext` value, the validator SHALL accept the key only if it exists in `ALLOWED_STRUCTURED_KEYS[learning_context]`, and SHALL discard all keys not in the allowed set.

**Validates: Requirements 4.5**

### Property 13: Proposal-to-PendingProfileChange mapping with source tagging

*For any* valid set of synthesized proposals from a document upload with job_id J, the pipeline SHALL create exactly one `PendingProfileChange` entry per proposed field change, each tagged with `source_type="document_upload"` and `session_id=J`. When `skip_review=false`, all proposals become pending changes. When `skip_review=true`, no pending changes are created and values are written directly to L1.

**Validates: Requirements 5.1, 5.4, 5.7**

### Property 14: Accumulation invariant — no L1 values are overwritten or removed

*For any* existing L1 profile state and any set of accepted document-upload proposals, the resulting profile SHALL contain all previously existing `focus_areas`, `style_notes`, and `learning_context_structured` key-value pairs that were present before the new proposals were applied. New values are appended/merged only.

**Validates: Requirements 7.1**

### Property 15: Focus area case-insensitive deduplication

*For any* proposed `focus_area` string and any existing list of focus areas, the synthesizer SHALL include the proposal only if no existing entry matches it under case-insensitive comparison. The resulting proposed list SHALL contain no case-insensitive duplicates relative to the existing list.

**Validates: Requirements 7.2**



---

## Error Handling

### Frontend Error Handling

| Scenario | Behavior |
|---|---|
| File exceeds 10 MB | Inline error on preview chip; file excluded from submission |
| Unsupported MIME type | Inline error listing supported formats; file excluded |
| More than 5 files selected | Accept first 5; show warning about max count |
| Network failure on upload | Error message + "Retry" button (re-uses selected files) |
| 3 consecutive retry failures | Disable retry; message "Upload unavailable, try again later" |
| Polling timeout (no response in 30s) | Show timeout message; allow chat to continue |
| Connection lost during polling | "Connection Lost" badge; "Refresh Status" button |

### Backend Error Handling

| Scenario | Behavior | HTTP Response |
|---|---|---|
| Unauthenticated request | Reject immediately | 401 |
| All files fail validation | Return detailed per-file errors | 400 |
| Batch exceeds 5 files | Reject entire request | 400 |
| File storage failure | Log error; return 500; no job created | 500 |
| Extraction fails (corrupted file) | Mark file as `failed`; continue other files | (background) |
| Extraction produces empty text | Mark file as `failed`; error: "no extractable content" | (background) |
| Password-protected file | Mark file as `failed`; error: "password-protected" | (background) |
| LLM timeout/rate-limit | Retry once after 2s; if retry fails, mark job `failed` | (background) |
| LLM malformed response | Discard proposals; log parsing failure; mark job `failed` | (background) |
| LLM produces no proposals | Mark job `done`; result: "no memory updates found" | (background) |

### Retry Strategy

```
Upload attempt → fails
  ├── Client stores file reference (no re-selection needed)
  ├── Retry 1 → fails
  ├── Retry 2 → fails
  ├── Retry 3 → fails
  └── Disable retry button, show "try again later"
      └── Re-enabled on page refresh or new session

LLM synthesis → fails
  ├── Wait 2 seconds
  ├── Retry 1 → fails
  └── Mark job `failed`
      └── Preserve extracted_text on job record (24h TTL)
      └── "Retry Analysis" button triggers new synthesis from preserved text
```

### Data Preservation

- Raw uploaded files: stored locally for 24 hours (TTL-based cleanup)
- Extracted text: preserved on the `Upload_Job` record for 24 hours when synthesis fails
- Both enable retry without re-upload, reducing user friction on transient failures

---

## Testing Strategy

### Unit Tests (pytest)

Unit tests cover specific examples, edge cases, and integration points:

- **Extraction edge cases**: empty files, password-protected files, corrupted binary data, files at exact size boundary (10 MB)
- **Validation examples**: specific MIME type checks, exact boundary conditions (5 files, 10 MB)
- **Status transitions**: job lifecycle state machine (pending → extracting → synthesizing → done/failed)
- **Proposal creation**: existing `accept_pending_change` path works with document-sourced proposals
- **Style note cap**: behavior when user has exactly 5 style notes and a new one is proposed
- **Skip Review mode**: direct write path vs. pending change creation

### Property-Based Tests (Hypothesis)

Property tests verify universal correctness guarantees. Each test runs **minimum 100 iterations** using the `hypothesis` library (already in `requirements.txt`).

**Configuration:**
- Library: `hypothesis` (Python, already installed)
- Min iterations: 100 per property (`@settings(max_examples=100)`)
- Each test tagged with design property reference

**Property test implementations:**

| Property | Test Module | Generator Strategy |
|---|---|---|
| P1: Client-side validation partition | `tests/property/test_file_validation.py` | Random file metadata (names, sizes, MIME types) |
| P2: Filename truncation/size formatting | `tests/property/test_file_formatting.py` | Random strings (0–500 chars), random ints (0–100MB) |
| P3: Server-side batch validation | `tests/property/test_upload_endpoint.py` | Random file batches (0–10 files, mixed valid/invalid) |
| P4: Tabular extraction row limits | `tests/property/test_extractors.py` | Random CSV/XLSX data (0–10,000 rows) |
| P5: JSON flattening | `tests/property/test_extractors.py` | Recursive JSON strategy (random nesting 0–15 levels, arrays 0–200 elements) |
| P6: UTF-8 invalid byte replacement | `tests/property/test_extractors.py` | Random byte sequences (mix of valid/invalid UTF-8) |
| P7: RTF text preservation | `tests/property/test_extractors.py` | Random text wrapped in RTF formatting |
| P8: Independent file processing | `tests/property/test_pipeline.py` | Random batches with mixed extractable/corrupted files |
| P9: Character truncation at sentence boundary | `tests/property/test_truncation.py` | Random text with sentences (50,000–200,000 chars) |
| P10: Token truncation at sentence boundary | `tests/property/test_truncation.py` | Random text with sentences (8,000–30,000 tokens) |
| P11: LLM output schema validation | `tests/property/test_synthesis.py` | Random JSON conforming/violating the schema |
| P12: Allowed structured keys | `tests/property/test_synthesis.py` | Random key-value pairs × all LearningContext values |
| P13: Proposal-to-PendingProfileChange mapping | `tests/property/test_pipeline.py` | Random valid proposal sets with job metadata |
| P14: Accumulation invariant | `tests/property/test_accumulation.py` | Random existing profiles + random proposals |
| P15: Focus area deduplication | `tests/property/test_accumulation.py` | Random strings with case variations |

**Tag format:**
```python
# Feature: chat-document-upload, Property 5: JSON flattening respects depth and array limits
@given(json_data=json_strategy())
@settings(max_examples=100)
def test_json_flattening_depth_and_array_limits(json_data):
    ...
```

### Integration Tests

- **End-to-end upload flow**: File upload → extraction → synthesis → proposals displayed
- **Pipeline independence**: Document pipeline operates while ingestion pipeline is unavailable
- **Existing accept/dismiss path**: Document-sourced proposals work with existing profile router
- **TTL cleanup**: Files and job records expire after 24 hours

### Dependencies (new packages needed)

Backend:
- `python-docx>=0.8.11` — DOCX text extraction
- `openpyxl>=3.1.0` — XLSX reading
- `striprtf>=0.0.26` — RTF to plain text

Frontend:
- No new dependencies required (uses native File API and existing fetch patterns)
