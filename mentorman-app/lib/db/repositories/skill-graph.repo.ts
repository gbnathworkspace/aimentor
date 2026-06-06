import connectDB from '../mongoose'
import { SkillGraphNodeModel } from '../models/skill-graph.model'
import { SkillGraphNode, SkillGraphNodeSchema, SkillGraphUpdate } from '@/lib/schemas'

export const SkillGraphRepo = {

  async getByTopic(userId: string, topic: string): Promise<SkillGraphNode | null> {
    await connectDB()
    const doc = await SkillGraphNodeModel.findOne({ userId, topic }).lean()
    if (!doc) return null
    return SkillGraphNodeSchema.parse(toPlain(doc))
  },

  async getAllForUser(userId: string): Promise<SkillGraphNode[]> {
    await connectDB()
    const docs = await SkillGraphNodeModel.find({ userId }).lean()
    return docs.map(doc => SkillGraphNodeSchema.parse(toPlain(doc)))
  },

  async getTopGaps(userId: string, limit = 3): Promise<SkillGraphNode[]> {
    await connectDB()
    const docs = await SkillGraphNodeModel
      .find({ userId })
      .sort({ gap: -1 })
      .limit(limit)
      .lean()
    return docs.map(doc => SkillGraphNodeSchema.parse(toPlain(doc)))
  },

  async getByTopics(userId: string, topics: string[]): Promise<SkillGraphNode[]> {
    await connectDB()
    const docs = await SkillGraphNodeModel
      .find({ userId, topic: { $in: topics } })
      .lean()
    return docs.map(doc => SkillGraphNodeSchema.parse(toPlain(doc)))
  },

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

  // Generic field patch — for partial field updates
  async patch(userId: string, topic: string, fields: Record<string, unknown>): Promise<SkillGraphNode | null> {
    await connectDB()
    const doc = await SkillGraphNodeModel.findOneAndUpdate(
      { userId, topic },
      { $set: fields },
      { new: true, lean: true }
    )
    if (!doc) return null
    return SkillGraphNodeSchema.parse(toPlain(doc))
  },

  async applyUpdate(userId: string, update: SkillGraphUpdate): Promise<SkillGraphNode | null> {
    await connectDB()
    const setFields: Record<string, unknown> = {
      current_level: update.new_level,
      gap:           update.gap,
      last_studied:  new Date().toISOString(),
    }
    if (update.weak_areas)   setFields['weak_areas']                  = update.weak_areas
    if (update.strong_areas) setFields['strong_areas']                = update.strong_areas
    if (update.eval_score)   setFields['signals.mentor_eval_score']   = update.eval_score
    const doc = await SkillGraphNodeModel.findOneAndUpdate(
      { userId, topic: update.topic },
      { $set: setFields, $inc: { 'signals.mentor_eval_count': 1 } },
      { new: true, lean: true }
    )
    if (!doc) return null
    return SkillGraphNodeSchema.parse(toPlain(doc))
  },

  async applyLeetCodeSignals(
    userId: string,
    topic: string,
    signals: { easy: number; medium: number; hard: number }
  ): Promise<void> {
    await connectDB()
    await SkillGraphNodeModel.updateOne(
      { userId, topic },
      { $set: { 'signals.leetcode_solved': signals, last_studied: new Date().toISOString() } }
    )
  },

  async delete(userId: string, topic: string): Promise<void> {
    await connectDB()
    await SkillGraphNodeModel.deleteOne({ userId, topic })
  },
}

function toPlain(doc: unknown): unknown {
  if (!doc) return doc
  const obj = doc as Record<string, unknown>
  const { _id, __v, createdAt, updatedAt, last_studied, ...rest } = obj
  void _id; void __v
  if (createdAt) rest['createdAt']    = (createdAt as Date).toISOString?.() ?? createdAt
  if (updatedAt) rest['updatedAt']    = (updatedAt as Date).toISOString?.() ?? updatedAt
  if (last_studied) rest['last_studied'] = (last_studied as Date).toISOString?.() ?? last_studied
  return rest
}
