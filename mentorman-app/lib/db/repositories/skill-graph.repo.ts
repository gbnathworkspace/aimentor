import connectDB from '../mongoose'
import { SkillGraphNodeModel } from '../models/skill-graph.model'
import {
  SkillGraphNode,
  SkillGraphNodeSchema,
  SkillGraphUpdate,
} from '@/lib/schemas'

// ─── SkillGraphRepo ───────────────────────────────────────────────────────────
// One document per (userId, topic). All writes are Zod-validated.
// This is the Layer 2 memory store — queried by topic for context assembly.

export const SkillGraphRepo = {

  // Get a single topic node — used by ContextAssembler
  async getByTopic(userId: string, topic: string): Promise<SkillGraphNode | null> {
    await connectDB()
    const doc = await SkillGraphNodeModel.findOne({ userId, topic }).lean()
    if (!doc) return null
    return SkillGraphNodeSchema.parse(toPlain(doc))
  },

  // Get all nodes for a user — used by SkillGraphPanel (Screen 5)
  async getAllForUser(userId: string): Promise<SkillGraphNode[]> {
    await connectDB()
    const docs = await SkillGraphNodeModel.find({ userId }).lean()
    return docs.map(doc => SkillGraphNodeSchema.parse(toPlain(doc)))
  },

  // Get top-N nodes by gap descending — used by "Biggest gaps" row
  async getTopGaps(userId: string, limit = 3): Promise<SkillGraphNode[]> {
    await connectDB()
    const docs = await SkillGraphNodeModel
      .find({ userId })
      .sort({ gap: -1 })
      .limit(limit)
      .lean()
    return docs.map(doc => SkillGraphNodeSchema.parse(toPlain(doc)))
  },

  // Get nodes by topic list — used by ContextAssembler (multi-topic sessions)
  async getByTopics(userId: string, topics: string[]): Promise<SkillGraphNode[]> {
    await connectDB()
    const docs = await SkillGraphNodeModel
      .find({ userId, topic: { $in: topics } })
      .lean()
    return docs.map(doc => SkillGraphNodeSchema.parse(toPlain(doc)))
  },

  // Upsert a full node — used by IngestionService (initial setup)
  async upsert(data: SkillGraphNode): Promise<SkillGraphNode> {
    await connectDB()
    const validated = SkillGraphNodeSchema.parse(data)
    const doc = await SkillGraphNodeModel.findOneAndUpdate(
      { userId: validated.userId, topic: validated.topic },
      { $set: validated },
      { upsert: true, new: true, lean: true }
    )
    return SkillGraphNodeSchema.parse(toPlain(doc))
  },

  // Apply an evaluation verdict update — used by EvaluationService
  // Only touches fields changed by the verdict, leaves signals intact
  async applyUpdate(userId: string, update: SkillGraphUpdate): Promise<SkillGraphNode | null> {
    await connectDB()
    const setFields: Record<string, unknown> = {
      current_level: update.new_level,
      gap: update.gap,
      last_studied: new Date().toISOString(),
    }
    if (update.weak_areas) setFields['weak_areas'] = update.weak_areas
    if (update.strong_areas) setFields['strong_areas'] = update.strong_areas
    if (update.eval_score) {
      setFields['signals.mentor_eval_score'] = update.eval_score
    }

    const doc = await SkillGraphNodeModel.findOneAndUpdate(
      { userId, topic: update.topic },
      {
        $set: setFields,
        $inc: { 'signals.mentor_eval_count': 1 },
      },
      { new: true, lean: true }
    )
    if (!doc) return null
    return SkillGraphNodeSchema.parse(toPlain(doc))
  },

  // Apply LeetCode signal update — used by IngestionService (CSV parse)
  async applyLeetCodeSignals(
    userId: string,
    topic: string,
    signals: { easy: number; medium: number; hard: number }
  ): Promise<void> {
    await connectDB()
    await SkillGraphNodeModel.updateOne(
      { userId, topic },
      {
        $set: {
          'signals.leetcode_solved': signals,
          last_studied: new Date().toISOString(),
        },
      }
    )
  },
}

function toPlain(doc: unknown): unknown {
  if (!doc) return doc
  const obj = doc as Record<string, unknown>
  const { _id, __v, ...rest } = obj
  void _id; void __v
  return JSON.parse(JSON.stringify(rest))
}
