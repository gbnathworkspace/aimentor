import mongoose, { Schema, Document, Model } from 'mongoose'
import { SkillGraphNode } from '@/lib/schemas'

export interface SkillGraphNodeDocument extends Omit<SkillGraphNode, 'last_studied' | 'createdAt' | 'updatedAt'>, Document {
  createdAt: Date
  updatedAt: Date
  last_studied?: Date
}

const SkillGraphNodeMongoSchema = new Schema<SkillGraphNodeDocument>(
  {
    userId:   { type: String, required: true, index: true },
    topic:    { type: String, required: true },
    category: { type: String, enum: ['DSA', 'Cloud', 'Core', 'System Design'] },
    required_level: {
      type: String, required: true,
      enum: ['novice', 'easy', 'medium', 'medium+', 'hard', 'expert'],
    },
    current_level: {
      type: String, required: true,
      enum: ['novice', 'easy', 'medium', 'medium+', 'hard', 'expert'],
    },
    gap:  { type: Number, required: true, min: 0, max: 100 },
    signals: {
      leetcode_solved: {
        easy:   { type: Number, default: 0, min: 0 },
        medium: { type: Number, default: 0, min: 0 },
        hard:   { type: Number, default: 0, min: 0 },
      },
      mentor_eval_score: { type: String },
      mentor_eval_count: { type: Number, default: 0, min: 0 },
    },
    strong_areas: { type: [String], default: [] },
    weak_areas:   { type: [String], default: [] },
    last_studied: { type: Date },
  },
  { timestamps: true, collection: 'skill_graph_nodes' }
)

SkillGraphNodeMongoSchema.index({ userId: 1, topic: 1 }, { unique: true })

export const SkillGraphNodeModel: Model<SkillGraphNodeDocument> =
  mongoose.models.SkillGraphNode ||
  mongoose.model<SkillGraphNodeDocument>('SkillGraphNode', SkillGraphNodeMongoSchema)
