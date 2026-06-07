import connectDB from '@/lib/db/mongoose'
import { ImmediateContextModel } from '@/lib/db/models/immediate-context.model'
import type { ImmediateContextDoc } from './types'

// ─── ImmediateContext Repository ──────────────────────────────────────────────
// Queries the ImmediateContext collection for active documents in a session.
// Used by the ContextAssembler on every LLM call to include uploaded file content.

export const ImmediateContextRepo = {
  /**
   * Fetches all active ImmediateContext documents for a session,
   * ordered by createdAt ascending (oldest first).
   */
  async getActiveForSession(sessionId: string): Promise<ImmediateContextDoc[]> {
    await connectDB()
    const docs = await ImmediateContextModel
      .find({ sessionId, active: true })
      .sort({ createdAt: 1 })
      .lean()

    return docs.map(doc => ({
      sessionId: doc.sessionId,
      userId: doc.userId,
      jobId: doc.jobId,
      filename: doc.filename,
      fileType: doc.fileType as 'resume' | 'leetcode',
      content: doc.content,
      tokenCount: doc.tokenCount,
      accompanyingMessage: doc.accompanyingMessage,
      active: doc.active,
      createdAt: doc.createdAt,
      updatedAt: doc.updatedAt,
    }))
  },
}
