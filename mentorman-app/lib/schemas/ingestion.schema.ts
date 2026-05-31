import { z } from 'zod'

// ─── Ingestion Job ────────────────────────────────────────────────────────────
// Tracks the state of a background ingestion job (resume PDF / LeetCode CSV).
// Created by FileUploadHandler, polled by UI via /api/ingest/[jobId]/status.

export const FileTypeSchema = z.enum(['resume', 'leetcode'])
export type FileType = z.infer<typeof FileTypeSchema>

export const IngestionFileSchema = z.object({
  s3Key: z.string(),                     // e.g. "uploads/userId/jobId/resume.pdf"
  originalName: z.string(),
  mimeType: z.string(),
  fileType: FileTypeSchema,
  sizeBytes: z.number().int().min(0),
})

export type IngestionFile = z.infer<typeof IngestionFileSchema>

export const IngestionStatusSchema = z.enum([
  'pending',      // uploaded, not yet processing
  'processing',   // extraction running
  'done',         // both structured + embedding paths complete
  'partial',      // structured facts saved, embedding failed (app still works)
  'failed',       // nothing saved, re-upload required
])

export type IngestionStatus = z.infer<typeof IngestionStatusSchema>

export const IngestionJobSchema = z.object({
  jobId: z.string(),
  userId: z.string(),
  status: IngestionStatusSchema,
  files: z.array(IngestionFileSchema),
  error: z.string().optional(),          // human-readable error for UI
  structuredDone: z.boolean().default(false),
  embeddingDone: z.boolean().default(false),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  completedAt: z.string().datetime().optional(),
})

export type IngestionJob = z.infer<typeof IngestionJobSchema>

// ─── Extracted content ────────────────────────────────────────────────────────

// From PDFExtractor — sectioned resume text
export const ResumeSectionSchema = z.object({
  section: z.enum([
    'work_experience',
    'education',
    'skills',
    'projects',
    'summary',
    'other',
  ]),
  text: z.string(),
  order: z.number().int().min(0),        // position in original document
})

export type ResumeSection = z.infer<typeof ResumeSectionSchema>

// From CSVExtractor — aggregated LeetCode stats per topic
export const LeetCodeTopicStatsSchema = z.object({
  topic: z.string(),                     // e.g. "graphs", "dynamic-programming"
  easy: z.number().int().min(0).default(0),
  medium: z.number().int().min(0).default(0),
  hard: z.number().int().min(0).default(0),
  total: z.number().int().min(0),
})

export type LeetCodeTopicStats = z.infer<typeof LeetCodeTopicStatsSchema>

// ─── Vector DB chunk metadata ─────────────────────────────────────────────────
// Stored alongside each embedding vector. Used by EpisodeSchema in retrieval.

export const ChunkMetadataSchema = z.object({
  userId: z.string(),
  source: z.enum(['resume', 'session_summary', 'doubt']),
  section: z.string().optional(),        // resume section, session topic, etc.
  topic: z.string().optional(),          // topic tag for TopicFilteredAssembler
  sessionId: z.string().optional(),
  jobId: z.string().optional(),
  chunkIndex: z.number().int().min(0),
  createdAt: z.string().datetime(),
})

export type ChunkMetadata = z.infer<typeof ChunkMetadataSchema>
