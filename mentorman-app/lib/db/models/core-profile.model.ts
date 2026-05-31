import mongoose, { Schema, Document, Model } from 'mongoose'
import { CoreProfile } from '@/lib/schemas'

// ─── Mongoose document type ───────────────────────────────────────────────────
export interface CoreProfileDocument extends Omit<CoreProfile, 'createdAt' | 'updatedAt'>, Document {
  createdAt: Date
  updatedAt: Date
}

// ─── Schema ───────────────────────────────────────────────────────────────────
const CoreProfileMongoSchema = new Schema<CoreProfileDocument>(
  {
    userId: { type: String, required: true, unique: true, index: true },
    goal: { type: String, required: true },
    targetDate: { type: String, required: true },
    availability: {
      weekdayHrs: { type: Number, required: true, min: 0, max: 24 },
      weekendHrs: { type: Number, required: true, min: 0, max: 24 },
      totalWeeklyHrs: { type: Number, required: true, min: 0 },
    },
    currentRole: { type: String },
    yearsOfExperience: { type: Number, min: 0 },
    education: {
      degree: { type: String },
      field: { type: String },
      institution: { type: String },
    },
    skills: { type: [String], default: [] },
  },
  {
    timestamps: true,   // auto-manages createdAt + updatedAt
    collection: 'core_profiles',
  }
)

// ─── Model (singleton pattern for Next.js hot reload) ────────────────────────
export const CoreProfileModel: Model<CoreProfileDocument> =
  mongoose.models.CoreProfile ||
  mongoose.model<CoreProfileDocument>('CoreProfile', CoreProfileMongoSchema)
