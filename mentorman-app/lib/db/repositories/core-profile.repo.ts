import connectDB from '../mongoose'
import { CoreProfileModel } from '../models/core-profile.model'
import { CoreProfile, CoreProfileSchema, CoreProfileUpdate } from '@/lib/schemas'

export const CoreProfileRepo = {

  async get(userId: string): Promise<CoreProfile | null> {
    await connectDB()
    const doc = await CoreProfileModel.findOne({ userId }).lean()
    if (!doc) return null
    return CoreProfileSchema.parse(toPlain(doc))
  },

  async upsert(data: CoreProfile): Promise<CoreProfile> {
    await connectDB()
    const validated = CoreProfileSchema.parse(data)
    const doc = await CoreProfileModel.findOneAndUpdate(
      { userId: validated.userId },
      { $set: validated },
      { upsert: true, new: true, lean: true }
    )
    return CoreProfileSchema.parse(toPlain(doc))
  },

  async update(userId: string, patch: CoreProfileUpdate): Promise<CoreProfile | null> {
    await connectDB()
    const doc = await CoreProfileModel.findOneAndUpdate(
      { userId },
      { $set: patch },
      { new: true, lean: true }
    )
    if (!doc) return null
    return CoreProfileSchema.parse(toPlain(doc))
  },

  async delete(userId: string): Promise<void> {
    await connectDB()
    await CoreProfileModel.deleteOne({ userId })
  },
}

function toPlain(doc: unknown): unknown {
  if (!doc) return doc
  const obj = doc as Record<string, unknown>
  const { _id, __v, createdAt, updatedAt, ...rest } = obj
  void _id; void __v; void createdAt; void updatedAt
  return rest
}
