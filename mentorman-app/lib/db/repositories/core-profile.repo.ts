import connectDB from '../mongoose'
import { CoreProfileModel } from '../models/core-profile.model'
import {
  CoreProfile,
  CoreProfileSchema,
  CoreProfileUpdate,
  CoreProfileUpdateSchema,
} from '@/lib/schemas'

// ─── CoreProfileRepo ──────────────────────────────────────────────────────────
// All reads Zod-validate before returning — if the DB shape drifts from the
// schema, it fails loud here rather than silently corrupting downstream.

export const CoreProfileRepo = {

  async get(userId: string): Promise<CoreProfile | null> {
    await connectDB()
    const doc = await CoreProfileModel.findOne({ userId }).lean()
    if (!doc) return null
    return CoreProfileSchema.parse(toPlain(doc))
  },

  async upsert(data: CoreProfile): Promise<CoreProfile> {
    await connectDB()
    // Validate input before write — schema is the contract
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
    const validated = CoreProfileUpdateSchema.parse(patch)
    const doc = await CoreProfileModel.findOneAndUpdate(
      { userId },
      { $set: validated },
      { new: true, lean: true }
    )
    if (!doc) return null
    return CoreProfileSchema.parse(toPlain(doc))
  },

  async exists(userId: string): Promise<boolean> {
    await connectDB()
    return CoreProfileModel.exists({ userId }) !== null
  },
}

// ─── Util: strip Mongoose internals before Zod parse ─────────────────────────
function toPlain(doc: unknown): unknown {
  if (!doc) return doc
  const obj = doc as Record<string, unknown>
  const { _id, __v, ...rest } = obj
  void _id; void __v  // unused, just stripping
  // Convert Date → ISO string to match Zod z.string().datetime()
  return JSON.parse(JSON.stringify(rest))
}
