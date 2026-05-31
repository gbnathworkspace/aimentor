import mongoose, { Schema, Document, Model } from 'mongoose'
import { Session } from '@/lib/schemas'

// ─── Mongoose document type ───────────────────────────────────────────────────
export interface SessionDocument
  extends Omit<Session, 'createdAt' | 'updatedAt' | 'endedAt'>,
    Document {
  createdAt: Date
  updatedAt: Date
  endedAt?: Date
}

// ─── Schema ───────────────────────────────────────────────────────────────────
const MessageMongoSchema = new Schema(
  {
    id: { type: String, required: true },
    role: { type: String, required: true, enum: ['mentor', 'user'] },
    content: { type: String, required: true },
    timestamp: { type: String, required: true },
    nudge: {
      message: { type: String },
      pinTopic: { type: String },
    },
  },
  { _id: false }  // messages are embedded, no separate _id needed
)

const SessionMongoSchema = new Schema<SessionDocument>(
  {
    sessionId: { type: String, required: true, unique: true, index: true },
    userId: { type: String, required: true, index: true },
    title: { type: String, required: true },
    mode: {
      type: String,
      required: true,
      enum: ['planning', 'topic', 'doubt', 'evaluation'],
    },
    topic: { type: String },
    status: {
      type: String,
      required: true,
      enum: ['active', 'ended', 'archived'],
      default: 'active',
    },
    messages: { type: [MessageMongoSchema], default: [] },
    tags: { type: [String], default: [] },
    summary: { type: String },
    endedAt: { type: Date },
    durationMinutes: { type: Number, min: 0 },
  },
  {
    timestamps: true,
    collection: 'sessions',
  }
)

// Index for sidebar session list (userId + most recent first)
SessionMongoSchema.index({ userId: 1, createdAt: -1 })

// ─── Model ────────────────────────────────────────────────────────────────────
export const SessionModel: Model<SessionDocument> =
  mongoose.models.Session ||
  mongoose.model<SessionDocument>('Session', SessionMongoSchema)
