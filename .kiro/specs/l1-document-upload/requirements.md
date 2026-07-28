# Requirements Document

## Introduction

L1 (Core Profile — `unified-backend/app/models/profile.py`) is currently populated
two ways: direct user input at onboarding (`ProfileCreate`/`ProfileUpdate`) and
LLM proposals from the post-session profiling agent, gated behind
`PendingProfileChange` accept/dismiss.

This feature adds a third input path: the user uploads a document (resume,
JD, cert syllabus, notes) and an extraction pass turns it into the same kind
of structured facts the profiling agent already proposes — merged into L1
only after the user confirms, and building up over multiple uploads rather
than a single doc replacing the last.

This is a new mechanism, not a repurposing of the two upload paths that
already exist:
- `session_upload.py` → `immediate_contexts` — session-scoped, injected as a
  4th prompt block, discarded when the session ends. Does not touch L1.
- `extraction.py` → `embeddings` — chunked + vector-embedded for retrieval.
  Does not touch L1.

Neither is reused here; both extract text from PDF/CSV already, so the
extraction step in this feature can share that code rather than re-parsing.

## Decisions carried in from scoping

| Question | Decision |
|---|---|
| Scope | General L1 enrichment (not just the subtopic-weights evidence box) |
| How extracted content lands in L1 | LLM-summarized into structured facts, not raw text |
| File types | PDF, DOC/DOCX, CSV, TXT |
| Re-upload behavior | Accumulates — each upload adds to a running list, not a single-slot replace |

## Open conflict to resolve before design

`ProposableField` (`profile.py:53-61`) is deliberately narrow today:
`goal_orientation`, `style_note`, `learning_context_structured`. Its docstring
is explicit — *"proposals never touch onboarding-owned fields (learning_context,
focus_areas, the three teaching preferences); those are direct user input, not
inferred."*

A resume will routinely imply `focus_areas` (e.g. "3 years React" →
`"React"`). Two ways to resolve, pick one before design.md:

1. **Documents stay inside the existing boundary.** Extraction only ever
   proposes `goal_orientation` / `style_note` / `learning_context_structured`
   — a resume's skills never populate `focus_areas`, only inform tone/context.
2. **Widen the boundary for this source only.** Add a new `ProposableField`
   (e.g. `FOCUS_AREAS_SUGGESTED`) that *can* touch `focus_areas`, on the
   reasoning that a document is still user-supplied evidence, not an LLM
   inference from a transcript — same trust tier as direct input.

## Requirements

### Requirement 1 — Upload entry point

**User Story:** As a user, I want to upload a document from my profile/settings
area, so that I don't have to manually type out what's already written down
somewhere.

#### Acceptance Criteria

1. WHEN the user is on the Settings > Memory screen THEN the system SHALL
   offer a document upload control alongside the existing memory-edit chat box.
2. WHEN the user selects a file THEN the system SHALL validate its MIME type
   and size before accepting the upload.
3. IF the file's type is not in the supported set THEN the system SHALL
   reject it with a specific error naming the allowed types, matching the
   existing error shape in `file_upload.py:validate_files`.

### Requirement 2 — Supported formats

**User Story:** As a user, I want to upload the format my document already
exists in, so that I don't have to convert it first.

#### Acceptance Criteria

1. WHEN the uploaded file is PDF THEN the system SHALL extract text using
   the same `pypdf` path as `session_upload.py:_extract_text`.
2. WHEN the uploaded file is CSV THEN the system SHALL extract text using
   the same row-flattening logic as `session_upload.py:_extract_text`.
3. WHEN the uploaded file is TXT THEN the system SHALL decode it as UTF-8
   with replacement, matching the existing fallback branch.
4. WHEN the uploaded file is DOC or DOCX THEN the system SHALL extract text
   via a new parser (nothing in the repo handles this format today —
   `python-docx` covers `.docx`; `.doc` — legacy binary — needs a separate
   library or should be rejected with a clear "re-save as .docx" message;
   decide which in design.md).
5. IF extraction produces no usable text THEN the system SHALL surface a
   failure state to the user rather than silently discarding the upload.

### Requirement 3 — Extraction → structured facts

**User Story:** As the system, I want to turn free-form document text into
the same shape L1 already understands, so that L1 stays within its token
budget instead of growing unbounded with raw text.

#### Acceptance Criteria

1. WHEN extracted text is available THEN the system SHALL run one LLM call
   that proposes structured field values in the shape defined by
   `ProposableField` (subject to the Requirement 3a widening decision above).
2. WHEN the LLM proposes a `learning_context_structured` value THEN the
   system SHALL restrict proposed keys to `ALLOWED_STRUCTURED_KEYS` for the
   user's current `learning_context`, same guard the profiling agent is
   documented to need but does not yet enforce (`profile.py:80-82`).
3. WHEN the LLM proposes a `style_note` THEN the system SHALL populate
   `source_quote` with a verbatim span from the extracted text, not a
   paraphrase — same requirement `StyleNote.source_quote` already documents.
4. IF the document is larger than the model's usable context THEN the system
   SHALL truncate or chunk it (cap TBD in design.md — `session_upload.py`
   uses no cap for the immediate-context path, but that path isn't
   summarized into a token-fixed field the way L1 is).

### Requirement 4 — User confirms before any L1 write

**User Story:** As a user, I want to see what a document implied about me
before it changes my profile, so that a bad extraction can't silently
corrupt L1.

#### Acceptance Criteria

1. WHEN extraction produces proposed field values THEN the system SHALL
   create `PendingProfileChange` entries, reusing the existing
   accept/dismiss flow (`profile.py` router: `pending-changes/{field}/accept`
   and `.../dismiss`) — not a new confirmation mechanism.
2. THE system SHALL NOT write extracted values directly to the profile
   document under any circumstance — matches the existing invariant stated
   on `PendingProfileChange` ("never auto-applied").
3. WHEN a `PendingProfileChange` from a document is accepted THEN the system
   SHALL apply it through the same `accept_pending_change` path already
   used for profiling-agent proposals, tagging its `session_id` field with
   a document reference instead of a session id (needs a schema note in
   design.md — `session_id: str` on `PendingProfileChange` is currently
   assumed to always be a real session).

### Requirement 5 — Uploads accumulate, not replace

**User Story:** As a user who uploads a resume today and a JD next month, I
want both to inform my profile, so that L1 reflects everything I've shared,
not just the most recent thing.

#### Acceptance Criteria

1. WHEN a new document is uploaded THEN the system SHALL NOT discard or
   overwrite facts derived from a previously-accepted document.
2. THE system SHALL maintain an audit list of uploaded documents (filename,
   uploaded_at, extraction status) capped at a fixed size, following the
   same FIFO drop-oldest pattern already used for `style_notes[:5]`
   (`profile.py:131-135`) rather than growing unbounded.
3. IF two documents imply conflicting values for the same field (e.g. two
   different `target_comp` figures) THEN the system SHALL surface both as
   separate pending changes rather than silently picking one — resolution
   order is the user's call via accept/dismiss, not the system's.

### Requirement 6 — L1 stays small

**User Story:** As the context assembler, I need L1 to stay near its ~200
token budget, so that adding document upload doesn't blow out every prompt's
cost regardless of session mode.

#### Acceptance Criteria

1. THE system SHALL NOT add raw or lightly-trimmed document text to any
   field injected into L1's prompt block.
2. WHEN `context_assembler.py` builds the L1 block THEN the token cost SHALL
   remain within the budget documented in the README (~200 tokens),
   verified by a token-count test similar to existing budget tests.

### Requirement 7 — Reuse existing upload plumbing

**User Story:** As the developer, I don't want a second file-validation and
storage implementation living next to the one that already exists.

#### Acceptance Criteria

1. THE system SHALL reuse `file_upload.py:validate_files` and
   `store_file`/`_store_local`/`_store_s3` for size/type validation and
   storage, extended only to add DOC/DOCX to `ALLOWED_MIME_TYPES` — not a
   parallel implementation.
2. THE system SHALL reuse the PDF/CSV extraction functions already shared
   between `session_upload.py` and `extraction.py`, rather than a third
   copy of PDF/CSV parsing logic.

## Out of scope

- Editing/deleting a document after upload (only accept/dismiss of the
  proposals it generated).
- Re-running extraction on an already-uploaded document.
- Any change to the `session_upload.py` (`immediate_contexts`) or
  `extraction.py` (`embeddings`) pipelines — both stay as they are.
