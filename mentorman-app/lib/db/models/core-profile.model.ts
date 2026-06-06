import mongoose, { Schema, Document, Model } from 'mongoose'
import { CoreProfile } from '@/lib/schemas'

export interface CoreProfileDocument extends CoreProfile, Document {}

const CoreProfileMongoSchema = new Schema<CoreProfileDocument>(
  {
    userId:             { type: String, required: true, unique: true, index: true },
    goal:               { type: String, required: true },
    deadline:           { type: String, required: true },
    overall_level:      { type: String, required: true, default: 'beginner' },
    daily_availability: { type: String, required: true },
    email:              { type: String, default: '' },
  },
  { timestamps: true, collection: 'core_profiles' }
)

export const CoreProfileModel: Model<CoreProfileDocument> =
  mongoose.models.CoreProfile ||
  mongoose.model<CoreProfileDocument>('CoreProfile', CoreProfileMongoSchema)
