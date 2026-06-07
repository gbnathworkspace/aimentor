/**
 * POST /api/session/[sessionId]/upload
 *
 * Session Upload Handler — receives file uploads during an active session,
 * validates them, stores to S3, creates a JobRecord, and enqueues extraction.
 *
 * Validation sequence:
 * 1. Authenticate via Clerk JWT
 * 2. Verify session exists and belongs to user (403 if not)
 * 3. Verify session is active (400 if ended)
 * 4. Check no other upload is pending/processing for this session (409)
 * 5. Delegate file type/size validation (400 on failure)
 * 6. Store to S3, create JobRecord with session metadata
 * 7. Return 202 with { jobId }
 */

import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { requireUserId } from '@/lib/auth'
import { SessionRepo } from '@/lib/db/repositories/session.repo'
import connectDB from '@/lib/db/mongoose'
import { IngestionJobModel } from '@/lib/db/models/ingestion-job.model'
import { validateUploadFile, truncateMessage } from '@/lib/chat-upload/utils'
import { getStorageBackend } from '@/lib/chat-upload/storage'

/** Maximum allowed file size in bytes (10 MB). */
const MAX_FILE_SIZE = 10_485_760

/** MIME types accepted for session uploads. */
const ALLOWED_MIME_TYPES: Record<string, 'resume' | 'leetcode'> = {
  'application/pdf': 'resume',
  'text/csv': 'leetcode',
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    // 1. Authenticate via Clerk JWT
    const userId = await requireUserId()
    const { sessionId } = await params

    await connectDB()

    // 2. Verify session exists and belongs to user
    const session = await SessionRepo.getById(sessionId)
    if (!session || session.userId !== userId) {
      return NextResponse.json(
        { error: 'Forbidden' },
        { status: 403 }
      )
    }

    // 3. Verify session is active (not ended/archived)
    if (session.status !== 'active') {
      return NextResponse.json(
        { error: 'Uploads not permitted on inactive sessions' },
        { status: 400 }
      )
    }

    // 4. Check for concurrent uploads — reject if another job is pending/processing
    const activeJob = await IngestionJobModel.findOne({
      session_id: sessionId,
      status: { $in: ['pending', 'processing'] },
    }).lean()

    if (activeJob) {
      return NextResponse.json(
        { error: 'A previous upload is still being processed' },
        { status: 409 }
      )
    }

    // Parse multipart form data
    const formData = await req.formData()
    const file = formData.get('file') as File | null
    const accompanyingMessageRaw = formData.get('accompanyingMessage') as string | null

    if (!file) {
      return NextResponse.json(
        { error: 'No file provided' },
        { status: 400 }
      )
    }

    // 5. Delegate file type/size validation
    const validationError = validateUploadFile({ name: file.name, size: file.size })
    if (validationError) {
      return NextResponse.json(
        { error: validationError },
        { status: 400 }
      )
    }

    // Additional MIME type check (server-side)
    const mimeType = file.type || ''
    const fileType = ALLOWED_MIME_TYPES[mimeType]
    if (!fileType) {
      // Fallback: infer from extension
      const ext = file.name.includes('.')
        ? `.${file.name.split('.').pop()?.toLowerCase()}`
        : ''
      if (ext === '.pdf') {
        // Accept as resume
      } else if (ext === '.csv') {
        // Accept as leetcode
      } else {
        return NextResponse.json(
          { error: 'Only .pdf and .csv files are supported' },
          { status: 400 }
        )
      }
    }

    // Determine file type from extension (authoritative source)
    const extension = file.name.includes('.')
      ? `.${file.name.split('.').pop()?.toLowerCase()}`
      : ''
    const resolvedFileType: 'resume' | 'leetcode' =
      extension === '.csv' ? 'leetcode' : 'resume'

    // Read file bytes
    const fileBuffer = Buffer.from(await file.arrayBuffer())

    // Validate actual size (belt-and-suspenders)
    if (fileBuffer.length === 0 || fileBuffer.length > MAX_FILE_SIZE) {
      return NextResponse.json(
        { error: 'File size is invalid. Must be between 1 byte and 10 MB.' },
        { status: 400 }
      )
    }

    // 6. Store file to S3 and create JobRecord
    const jobId = randomUUID()
    const contentType = mimeType || (extension === '.csv' ? 'text/csv' : 'application/pdf')

    const s3Key = await getStorageBackend().upload(userId, jobId, file.name, fileBuffer, contentType)

    // Truncate accompanying message to 2000 chars, default to empty string
    const accompanyingMessage = truncateMessage(accompanyingMessageRaw ?? '', 2000)

    const now = new Date()
    await IngestionJobModel.create({
      job_id: jobId,
      user_id: userId,
      status: 'pending',
      files: [
        {
          filename: file.name,
          mime_type: contentType,
          size_bytes: fileBuffer.length,
          s3_key: s3Key,
        },
      ],
      source_category: resolvedFileType,
      session_id: sessionId,
      upload_context: 'session',
      accompanying_message: accompanyingMessage,
      extraction_ready: false,
      structured_done: false,
      embedding_done: false,
      created_at: now,
      updated_at: now,
    })

    // 7. Trigger extraction in the ingestion pipeline — fire and forget
    const apiBase = process.env.MENTORMAN_API_BASE ?? 'http://localhost:8000'
    fetch(`${apiBase}/api/ingest/trigger`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
      },
      body: JSON.stringify({ job_id: jobId }),
    }).catch(err => console.error('Failed to trigger extraction pipeline:', err))

    return NextResponse.json({ jobId }, { status: 202 })
  } catch (err) {
    console.error('Session upload error:', err)

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
