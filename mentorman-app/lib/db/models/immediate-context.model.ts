import mongoose, { Schema, Document, Model } from 'mongoose'
import { FileType } from '@/lib/schemas'

// ─── ImmediateContext document type ───────────────────────────────────────────
export interface ImmediateContextDocument extends Document {
  sessionId: string
  userId: string
  jobId: string
  filename: string
  fileType: FileType
  content: string
  tokenCount: number
  accompanyingMessage: string
  active: boolean
  createdAt: Date
  updatedAt: Date
}

// ─── Schema ───────────────────────────────────────────────────────────────────
const ImmediateContextMongoSchema = new Schema<ImmediateContextDocument>(
  {
    sessionId:          { type: String, required: true },
    userId:             { type: String, required: true },
    jobId:              { type: String, required: true },
    filename:           { type: String, required: true },
    fileType:           { type: String, required: true, enum: ['resume', 'leetcode'] },
    content:            { type: String, required: true },
    tokenCount:         { type: Number, required: true, min: 0 },
    accompanyingMessage: { type: String, default: '' },
    active:             { type: Boolean, required: true, default: true },
  },
  {
    timestamps: true,
    collection: 'immediate_contexts',
  }
)

// ─── Indexes ──────────────────────────────────────────────────────────────────

// Compound index — used by ContextAssembler on every LLM call
ImmediateContextMongoSchema.index({ sessionId: 1, active: 1 })

// Index on jobId — used by deactivation
ImmediateContextMongoSchema.index({ jobId: 1 })

// TTL index — auto-expire documents 24 hours after creation
ImmediateContextMongoSchema.index({ createdAt: 1 }, { expireAfterSeconds: 86400 })

// ─── Model ────────────────────────────────────────────────────────────────────
export const ImmediateContextModel: Model<ImmediateContextDocument> =
  mongoose.models.ImmediateContext ||
  mongoose.model<ImmediateContextDocument>('ImmediateContext', ImmediateContextMongoSchema)
