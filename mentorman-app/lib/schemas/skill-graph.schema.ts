import { z } from 'zod'
import { LevelSchema, CategorySchema } from './shared.schema'

// ─── Skill Graph Node ─────────────────────────────────────────────────────────
// Layer 2 memory — one document per (userId, topic).

export const LeetCodeSignalsSchema = z.object({
  easy:   z.number().int().min(0).default(0),
  medium: z.number().int().min(0).default(0),
  hard:   z.number().int().min(0).default(0),
})

export const SignalsSchema = z.object({
  leetcode_solved:   LeetCodeSignalsSchema.optional(),
  mentor_eval_score: z.string().optional(),
  mentor_eval_count: z.number().int().min(0).default(0),
})

export const SkillGraphNodeSchema = z.object({
  userId:         z.string(),
  topic:          z.string(),
  category:       CategorySchema.optional(),   // not always provided by the frontend
  required_level: LevelSchema,
  current_level:  LevelSchema,
  gap:            z.number().min(0).max(100),
  signals:        SignalsSchema.optional(),
  strong_areas:   z.array(z.string()).default([]),
  weak_areas:     z.array(z.string()).default([]),
  last_studied:   z.string().optional(),
  createdAt:      z.string().optional(),
  updatedAt:      z.string().optional(),
})

export type SkillGraphNode = z.infer<typeof SkillGraphNodeSchema>
export type Signals = z.infer<typeof SignalsSchema>

export const SkillGraphUpdateSchema = z.object({
  topic:        z.string(),
  new_level:    LevelSchema,
  gap:          z.number().min(0).max(100),
  strong_areas: z.array(z.string()).optional(),
  weak_areas:   z.array(z.string()).optional(),
  eval_score:   z.string().optional(),
})

export type SkillGraphUpdate = z.infer<typeof SkillGraphUpdateSchema>

export const SkillUpdateToolSchema = z.object({
  topic:        z.string(),
  new_level:    LevelSchema,
  gap:          z.number().min(0).max(100),
  weak_areas:   z.array(z.string()).default([]),
  strong_areas: z.array(z.string()).default([]),
})

export type SkillUpdateTool = z.infer<typeof SkillUpdateToolSchema>
