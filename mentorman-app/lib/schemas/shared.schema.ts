import { z } from 'zod'

// ─── Shared enums used across multiple schemas ───────────────────────────────

export const LevelSchema = z.enum([
  'novice',
  'easy',
  'medium',
  'medium+',
  'hard',
  'expert',
])
export type Level = z.infer<typeof LevelSchema>

export const CategorySchema = z.enum(['DSA', 'Cloud', 'Core', 'System Design'])
export type Category = z.infer<typeof CategorySchema>

export const SessionModeSchema = z.enum([
  'planning',
  'topic',
  'doubt',
  'evaluation',
])
export type SessionMode = z.infer<typeof SessionModeSchema>

export const SessionStatusSchema = z.enum(['active', 'ended', 'archived'])
export type SessionStatus = z.infer<typeof SessionStatusSchema>
