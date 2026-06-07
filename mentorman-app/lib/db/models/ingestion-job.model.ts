import mongoose, { Schema, Document, Model } from 'mongoose'

// ─── IngestionJob document type ───────────────────────────────────────────────
// Mirrors the Python JobRecord stored in the `ingestion_jobs` collection.
// Used by the session upload handler to create jobs and check for concurrent uploads.
export interface IngestionJobDocument extends Document {
  job_id: string
  user_id: string
  status: 'pending' | 'processing' | 'done' | 'partial' | 'failed'
  files: Array<{
    filename: string
    mime_type: string
    size_bytes: number
    s3_key: string
  }>
  error?: string
  structured_done: boolean
  embedding_done: boolean
  source_category?: string
  session_id?: string
  upload_context?: string
  accompanying_message?: string
  extraction_ready?: boolean
  created_at: Date
  updated_at: Date
  completed_at?: Date
}

// ─── Schema ───────────────────────────────────────────────────────────────────
const IngestionFileSubSchema = new Schema(
  {
    filename:   { type: String, required: true },
    mime_type:  { type: String, required: true },
    size_bytes: { type: Number, required: true },
    s3_key:    { type: String, required: true },
  },
  { _id: false }
)

const IngestionJobMongoSchema = new Schema<IngestionJobDocument>(
  {
    job_id:              { type: String, required: true, unique: true, index: true },
    user_id:             { type: String, required: true, index: true },
    status:              { type: String, required: true, enum: ['pending', 'processing', 'done', 'partial', 'failed'], default: 'pending' },
    files:               { type: [IngestionFileSubSchema], default: [] },
    error:               { type: String },
    structured_done:     { type: Boolean, default: false },
    embedding_done:      { type: Boolean, default: false },
    source_category:     { type: String },
    session_id:          { type: String },
    upload_context:      { type: String },
    accompanying_message: { type: String },
    extraction_ready:    { type: Boolean, default: false },
    created_at:          { type: Date, required: true },
    updated_at:          { type: Date, required: true },
    completed_at:        { type: Date },
  },
  {
    collection: 'ingestion_jobs',
    // Disable Mongoose timestamps — we manage created_at/updated_at manually
    // to match the Python pipeline's field names
    timestamps: false,
  }
)

// Index for concurrent upload check: find active jobs for a given session
IngestionJobMongoSchema.index({ session_id: 1, status: 1 })

// ─── Model ────────────────────────────────────────────────────────────────────
export const IngestionJobModel: Model<IngestionJobDocument> =
  mongoose.models.IngestionJob ||
  mongoose.model<IngestionJobDocument>('IngestionJob', IngestionJobMongoSchema)
