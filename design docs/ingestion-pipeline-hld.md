# Ingestion Pipeline — High-Level Design

> **Status:** Design / pre-implementation  
> **Scope:** File upload → extraction → chunking + embedding → MongoDB + Vector DB  
> **Blocks:** Onboarding (Screens 1 + 7), SkillGraphService initial population

---

## Problem Statement

At the end of onboarding the user uploads two files — `resume.pdf` and `leetcode_export.csv`. The app needs to turn these into two things:

1. **Structured facts** (solved counts, difficulty breakdown, current role, years of experience) → written to MongoDB as the initial Core Profile and Skill Graph signals
2. **Searchable narrative** (work history, project descriptions, skills) → embedded and stored in the Vector DB for episodic retrieval

These are different shapes of data going to different stores. The pipeline must handle both without conflating them.

---

## Design Decisions

### Async processing — upload returns immediately
Extraction and embedding are slow (2–10 seconds for a PDF). The upload handler returns a `jobId` immediately. The UI polls `/api/ingest/[jobId]/status` and shows a progress indicator. Onboarding continues once the job completes.

### Two paths, one router
After extraction, the `IngestionRouter` splits content into two independent paths:
- **Structured path** → `StructuredParser` → MongoDB
- **Narrative path** → `ChunkerService` → `EmbedderService` → Vector DB

These run in parallel after the split.

### S3 for raw file storage
Raw files are stored in S3 with a 24-hour TTL before processing. This decouples the upload (synchronous, user-facing) from the extraction job (asynchronous, background). If extraction fails, the file can be re-processed from S3 without asking the user to re-upload.

---

## Components

### `FileUploadHandler`
- Validates file type (`application/pdf`, `text/csv`) and size (max 10MB)
- Stores raw file to S3 under `uploads/{userId}/{jobId}/{filename}`
- Creates a job record in MongoDB: `{ jobId, userId, status: 'pending', files: [...] }`
- Enqueues the extraction job
- Returns `{ jobId }` to the client immediately

### `ExtractorService`
Routes to the correct extractor based on MIME type.

**`PDFExtractor`**
- Uses `pdf-parse` to extract raw text
- Detects section headings (Work Experience, Education, Skills, Projects) using regex + heuristics
- Returns structured sections: `{ section: 'work_experience', text: '...' }[]`
- Preserves heading structure — critical for section-aware chunking downstream

**`CSVExtractor`**
- Uses `papaparse` with typed column definitions
- Aggregates rows by `topic` and `difficulty` columns
- Returns: `{ topic: 'graphs', easy: 4, medium: 2, hard: 0 }[]`
- Validates that required columns exist (`title`, `difficulty`, `status`) — fails loudly if the CSV format doesn't match

### `IngestionRouter`
After extraction, determines what goes where:

| Content | Path | Why |
|---|---|---|
| LeetCode aggregates | Structured → MongoDB | Countable facts, not searchable narrative |
| Resume work history | Both paths | Structured: current role + YOE. Narrative: full text for RAG |
| Resume skills section | Structured → MongoDB | Tags for Skill Graph |
| Resume project descriptions | Narrative → Vector DB | Useful for episodic context, not structured |
| Resume education | Structured → MongoDB | Degree, institution — stable facts |

### `StructuredParser`
Extracts typed facts and writes them to MongoDB via the relevant repositories.

**From LeetCode CSV:**
```typescript
// writes to SkillGraphRepo
{
  topic: 'graphs',
  signals: {
    leetcode_solved: { easy: 4, medium: 2, hard: 0 }
  }
}
```

**From Resume:**
```typescript
// writes to CoreProfileRepo
{
  currentRole: 'SWE II',
  yearsOfExperience: 3,
  education: { degree: 'B.Tech', field: 'CS' },
  skills: ['Python', 'AWS', 'System Design']
}
```

All writes are Zod-validated before hitting the DB.

### `ChunkerService`
Splits narrative text into chunks suitable for embedding.

**Strategy: section-aware chunking (not fixed-size)**

For resume PDFs, fixed-size chunking (e.g., 512 tokens with overlap) is wrong — it splits work experience entries mid-sentence, destroying the context. Section-aware chunking keeps each work experience entry as one chunk.

```
Work Experience:
  [chunk 1] SWE II at Razorpay · Jan 2022–present · built payment gateway...
  [chunk 2] Intern at Flipkart · May 2021–Jul 2021 · worked on...

Skills:
  [chunk 3] Python, AWS, Kafka, Redis, React...
```

Rules:
- Max chunk size: 512 tokens
- If a section exceeds 512 tokens, split at sentence boundaries with 10% overlap
- Each chunk carries metadata: `{ userId, source: 'resume', section: 'work_experience', chunkIndex: 0 }`

### `EmbedderService`
- Calls `EmbeddingProvider` (currently `VoyageProvider`) per chunk
- Stores to Vector DB: `{ vector, text, metadata }`
- Metadata must include `topic` tag when determinable (used by `TopicFilteredAssembler`)
- Runs chunk embedding in batches of 20 to avoid rate limits

---

## Data Flow

```
User uploads files (onboarding UI)
        ↓
FileUploadHandler
  ├── validates + stores to S3
  ├── creates job in MongoDB { status: 'pending' }
  └── returns jobId → client polls status

[background job starts]
        ↓
ExtractorService
  ├── PDFExtractor → sectioned text
  └── CSVExtractor → aggregated rows
        ↓
IngestionRouter
  ├── [structured path] ────────────────────────────────────────┐
  │     StructuredParser                                         │
  │       ├── writes CoreProfile → MongoDB                       │
  │       └── writes Skill Graph signals → MongoDB              │
  │                                                              ↓
  └── [narrative path]                                    job status → 'done'
        ChunkerService → EmbedderService → Vector DB
```

---

## Error Handling

| Failure point | Behaviour |
|---|---|
| Invalid file type | Reject at upload, return 400 immediately |
| S3 upload fails | Return 500, no job created |
| PDF parse fails | Mark job `failed`, surface error in UI — "Could not read PDF, try re-uploading" |
| CSV column missing | Mark job `failed`, surface specific column name in error |
| Embedding API down | Retry 3× with exponential backoff, then mark job `partial` — structured path still completes |
| Zod validation fails on write | Log + alert, do not write corrupted data, mark job `failed` |

The UI distinguishes between `partial` (structured facts saved, embeddings failed — app still works, RAG just won't have resume context) and `failed` (nothing saved, re-upload required).

---

## File Structure

```
src/
  lib/
    ingestion/
      handler.ts              ← FileUploadHandler
      router.ts               ← IngestionRouter
      extractors/
        pdf.extractor.ts
        csv.extractor.ts
      parsers/
        structured.parser.ts
      chunker/
        chunker.service.ts
      embedder/
        embedder.service.ts
  app/
    api/
      ingest/
        route.ts              ← POST /api/ingest (upload endpoint)
        [jobId]/
          status/
            route.ts          ← GET /api/ingest/[jobId]/status
```

---

## Open Questions

- [ ] Job queue implementation — simple MongoDB polling or a proper queue (BullMQ, Inngest)? For MVP, MongoDB polling is fine. Switch to Inngest if jobs start backing up.
- [ ] Re-ingestion — if the user re-uploads a newer resume, do we delete old chunks or append? Decision needed before implementing `FileUploadHandler`.
- [ ] LeetCode CSV format — verify the exact column names from a real export before writing `CSVExtractor`. The validator will fail loudly if they differ.
- [ ] Chunk size tuning — 512 tokens is a starting point. Measure retrieval quality after a few sessions and adjust.
