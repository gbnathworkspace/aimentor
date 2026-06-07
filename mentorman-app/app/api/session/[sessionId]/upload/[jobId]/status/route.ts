/**
 * GET /api/session/[sessionId]/upload/[jobId]/status
 *
 * Job Status Endpoint — returns the current status of an ingestion job,
 * including extraction readiness and a human-readable summary.
 *
 * Validation sequence:
 * 1. Authenticate via Clerk JWT
 * 2. Verify session exists and belongs to user (403 if not)
 * 3. Look up IngestionJob by job_id + session_id (404 if not found)
 * 4. Generate summary when extractionReady is true
 * 5. Return { jobId, status, extractionReady, summary?, error? }
 */

import { NextRequest, NextResponse } from 'next/server'
import { requireUserId } from '@/lib/auth'
import { SessionRepo } from '@/lib/db/repositories/session.repo'
import connectDB from '@/lib/db/mongoose'
import { IngestionJobModel } from '@/lib/db/models/ingestion-job.model'

/**
 * Generates a human-readable summary (max 80 chars) based on source category
 * and job metadata when extraction is ready.
 */
function generateSummary(job: {
  source_category?: string
  files: Array<{ filename: string }>
}): string {
  const category = job.source_category
  const filename = job.files?.[0]?.filename ?? 'file'

  if (category === 'leetcode') {
    return truncateSummary(`LeetCode: data extracted from ${filename}`)
  }

  if (category === 'resume') {
    return truncateSummary(`Resume: content extracted from ${filename}`)
  }

  return truncateSummary(`File processed: ${filename}`)
}

/** Ensures summary never exceeds 80 characters. */
function truncateSummary(summary: string): string {
  if (summary.length <= 80) return summary
  return summary.slice(0, 77) + '...'
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string; jobId: string }> }
) {
  try {
    // 1. Authenticate via Clerk JWT
    const userId = await requireUserId()
    const { sessionId, jobId } = await params

    await connectDB()

    // 2. Verify session exists and belongs to user
    const session = await SessionRepo.getById(sessionId)
    if (!session || session.userId !== userId) {
      return NextResponse.json(
        { error: 'Forbidden' },
        { status: 403 }
      )
    }

    // 3. Look up IngestionJob by job_id + session_id
    const job = await IngestionJobModel.findOne({
      job_id: jobId,
      session_id: sessionId,
    }).lean()

    if (!job) {
      return NextResponse.json(
        { error: 'Job not found' },
        { status: 404 }
      )
    }

    // 4. Build response
    const extractionReady = job.extraction_ready ?? false

    // Generate summary when extraction is ready
    const summary = extractionReady ? generateSummary(job) : undefined

    // Include error only when job has failed
    const error = job.status === 'failed' ? job.error : undefined

    return NextResponse.json({
      jobId: job.job_id,
      status: job.status,
      extractionReady,
      ...(summary && { summary }),
      ...(error && { error }),
    })
  } catch (err) {
    console.error('Job status error:', err)

    // Handle auth errors specifically
    if (err instanceof Error && err.message.includes('Unauthorized')) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
