import { encoding_for_model } from 'tiktoken'
import type { LeetCodeTopicStats, FileType } from '@/lib/schemas'

// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_TOKENS = 4000
const TOKENIZER_MODEL = 'gpt-4' // uses cl100k_base encoding

// ─── Types ────────────────────────────────────────────────────────────────────
export interface CreateImmediateContextParams {
  sessionId: string
  userId: string
  jobId: string
  filename: string
  fileType: FileType
  extractedContent: string | LeetCodeTopicStats[]
}

// ─── Token truncation ─────────────────────────────────────────────────────────

/**
 * Truncates text to fit within a token limit, splitting only at sentence
 * boundaries. Sentence boundaries are defined as `.`, `!`, or `?` followed
 * by whitespace or end of string.
 *
 * Returns the original text if it fits within the limit.
 */
export function truncateToTokenLimit(text: string, maxTokens: number = MAX_TOKENS): { content: string; tokenCount: number } {
  const enc = encoding_for_model(TOKENIZER_MODEL)

  try {
    const tokens = enc.encode(text)

    if (tokens.length <= maxTokens) {
      return { content: text, tokenCount: tokens.length }
    }

    // Decode the first maxTokens tokens back to text
    const truncatedBytes = enc.decode(tokens.slice(0, maxTokens))
    const truncatedText = new TextDecoder().decode(truncatedBytes)

    // Find the last sentence boundary in the truncated text
    // Sentence boundaries: `.`, `!`, `?` followed by whitespace or end of string
    const sentenceBoundaryRegex = /[.!?](?:\s|$)/g
    let lastBoundaryEnd = -1
    let match: RegExpExecArray | null

    while ((match = sentenceBoundaryRegex.exec(truncatedText)) !== null) {
      // Include the punctuation but not the trailing whitespace for the boundary
      lastBoundaryEnd = match.index + 1
    }

    // If no sentence boundary found, return the full truncated text
    // (edge case: single very long sentence)
    const finalContent = lastBoundaryEnd > 0
      ? truncatedText.slice(0, lastBoundaryEnd)
      : truncatedText

    const finalTokens = enc.encode(finalContent)
    return { content: finalContent, tokenCount: finalTokens.length }
  } finally {
    enc.free()
  }
}

// ─── CSV summarization ────────────────────────────────────────────────────────

/**
 * Converts an array of LeetCodeTopicStats into a human-readable summary.
 *
 * Format:
 * LeetCode Summary:
 * - Arrays: 12 easy, 5 medium, 1 hard (18 total)
 * - Graphs: 4 easy, 2 medium, 0 hard (6 total)
 */
export function summarizeLeetCodeStats(stats: LeetCodeTopicStats[]): string {
  const lines = stats.map(({ topic, easy, medium, hard }) => {
    const total = easy + medium + hard
    return `- ${topic}: ${easy} easy, ${medium} medium, ${hard} hard (${total} total)`
  })

  return `LeetCode Summary:\n${lines.join('\n')}`
}

// ─── Session Context Injector ─────────────────────────────────────────────────

export const SessionContextInjector = {
  /**
   * Creates an ImmediateContext document from extracted file content.
   * Called after extraction completes for a session-uploaded file.
   *
   * - For PDF (resume): tokenizes text and truncates to 4000 tokens at sentence boundaries
   * - For CSV (leetcode): generates a human-readable summary with topic/difficulty counts
   *
   * Retries the MongoDB write once on failure. Marks the job as `failed` if retry also fails.
   */
  async createImmediateContext(params: CreateImmediateContextParams): Promise<void> {
    // Dynamic imports to avoid triggering env validation at module load time
    const { default: connectDB } = await import('@/lib/db/mongoose')
    const { ImmediateContextModel } = await import('@/lib/db/models/immediate-context.model')
    const mongoose = await import('mongoose')

    const { sessionId, userId, jobId, filename, fileType, extractedContent } = params
    await connectDB()

    // Prepare content based on file type
    let content: string
    let tokenCount: number

    if (fileType === 'leetcode' && Array.isArray(extractedContent)) {
      // CSV: generate human-readable summary
      content = summarizeLeetCodeStats(extractedContent as LeetCodeTopicStats[])
      const enc = encoding_for_model(TOKENIZER_MODEL)
      try {
        tokenCount = enc.encode(content).length
      } finally {
        enc.free()
      }
    } else {
      // PDF: tokenize and truncate if needed
      const result = truncateToTokenLimit(extractedContent as string, MAX_TOKENS)
      content = result.content
      tokenCount = result.tokenCount
    }

    // Attempt to write to MongoDB (with one retry on failure)
    const docData = {
      sessionId,
      userId,
      jobId,
      filename,
      fileType,
      content,
      tokenCount,
      accompanyingMessage: '',
      active: true,
    }

    let writeSucceeded = false

    try {
      await ImmediateContextModel.create(docData)
      writeSucceeded = true
    } catch {
      // First attempt failed — retry once
      try {
        await ImmediateContextModel.create(docData)
        writeSucceeded = true
      } catch {
        // Both attempts failed — mark job as failed
        writeSucceeded = false
      }
    }

    if (!writeSucceeded) {
      // Mark job as failed
      const collection = mongoose.default.connection.collection('ingestion_jobs')
      await collection.updateOne(
        { job_id: jobId },
        {
          $set: {
            status: 'failed',
            error: 'Immediate context storage was unsuccessful',
            updated_at: new Date(),
          },
        }
      )
      return
    }

    // Update JobRecord with extractionReady: true
    const collection = mongoose.default.connection.collection('ingestion_jobs')
    await collection.updateOne(
      { job_id: jobId },
      {
        $set: {
          extraction_ready: true,
          updated_at: new Date(),
        },
      }
    )
  },

  /**
   * Marks the ImmediateContext as inactive when full ingestion completes.
   * After deactivation, the content is served exclusively through Episodic RAG.
   */
  async deactivateImmediateContext(jobId: string): Promise<void> {
    const { default: connectDB } = await import('@/lib/db/mongoose')
    const { ImmediateContextModel } = await import('@/lib/db/models/immediate-context.model')

    await connectDB()
    await ImmediateContextModel.updateOne(
      { jobId },
      { $set: { active: false } }
    )
  },
}
