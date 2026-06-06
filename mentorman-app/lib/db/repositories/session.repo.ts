import connectDB from '../mongoose'
import { SessionModel } from '../models/session.model'
import {
  Session,
  SessionSchema,
  SessionListItem,
  SessionListItemSchema,
  Message,
} from '@/lib/schemas'

// ─── SessionRepo ──────────────────────────────────────────────────────────────
// Handles session persistence. Messages are embedded in the session document.
// Sessions are created when a chat starts and saved in full after stream ends.

export const SessionRepo = {

  // Get a full session with all messages — used by ChatPanel, EvalPanel
  async getById(sessionId: string): Promise<Session | null> {
    await connectDB()
    const doc = await SessionModel.findOne({ sessionId }).lean()
    if (!doc) return null
    return SessionSchema.parse(toPlain(doc))
  },

  // Get sidebar list — lightweight, no messages loaded
  async listForUser(userId: string, limit = 50): Promise<SessionListItem[]> {
    await connectDB()
    const docs = await SessionModel
      .find({ userId })
      .sort({ createdAt: -1 })
      .limit(limit)
      .select('-messages')   // keep summary for context assembly; skip messages (heavy)
      .lean()
    return docs.map(doc => SessionListItemSchema.parse(toPlain(doc)))
  },

  // Create a new active session — called at session start
  async create(data: Session): Promise<Session> {
    await connectDB()
    const validated = SessionSchema.parse(data)
    const doc = await SessionModel.create(validated)
    return SessionSchema.parse(toPlain(doc.toObject()))
  },

  // Save full session after stream closes (SessionSaveHandler)
  async save(sessionId: string, messages: Message[], summary?: string): Promise<Session | null> {
    await connectDB()
    const doc = await SessionModel.findOneAndUpdate(
      { sessionId },
      {
        $set: {
          messages,
          summary,
          status: 'ended',
          endedAt: new Date().toISOString(),
        },
      },
      { new: true, lean: true }
    )
    if (!doc) return null
    return SessionSchema.parse(toPlain(doc))
  },

  // Archive a session — makes it read-only in the sidebar
  async archive(sessionId: string): Promise<void> {
    await connectDB()
    await SessionModel.updateOne(
      { sessionId },
      { $set: { status: 'archived' } }
    )
  },

  // Update title — called after auto-title generation (post-stream Haiku call)
  async updateTitle(sessionId: string, title: string): Promise<void> {
    await connectDB()
    await SessionModel.updateOne(
      { sessionId },
      { $set: { title } }
    )
  },

  // Update duration — calculated from createdAt → endedAt
  async updateDuration(sessionId: string, durationMinutes: number): Promise<void> {
    await connectDB()
    await SessionModel.updateOne(
      { sessionId },
      { $set: { durationMinutes } }
    )
  },

  async exists(sessionId: string): Promise<boolean> {
    await connectDB()
    return SessionModel.exists({ sessionId }) !== null
  },

  async delete(sessionId: string): Promise<void> {
    await connectDB()
    await SessionModel.deleteOne({ sessionId })
  },
}

function toPlain(doc: unknown): unknown {
  if (!doc) return doc
  const obj = doc as Record<string, unknown>
  const { _id, __v, ...rest } = obj
  void _id; void __v
  return JSON.parse(JSON.stringify(rest))
}
