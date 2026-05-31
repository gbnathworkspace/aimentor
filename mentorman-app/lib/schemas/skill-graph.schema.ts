import { z } from 'zod'
import { LevelSchema, CategorySchema } from './shared.schema'

// ─── Skill Graph Node ─────────────────────────────────────────────────────────
// Layer 2 memory — queried by topic and injected into the LLM call.
// One document per (userId, topic) pair.
// Written by: IngestionService (LeetCode CSV), EvaluationService (verdict).
// Read by: ContextAssembler (per topic), SkillGraphPanel (UI Screen 5).

export const LeetCodeSignalsSchema = z.object({
  easy: z.number().int().min(0).default(0),
  medium: z.number().int().min(0).default(0),
  hard: z.number().int().min(0).default(0),
})

export const SignalsSchema = z.object({
  leetcode_solved: LeetCodeSignalsSchema.optional(),
  mentor_eval_score: z.string().optional(), // e.g. "3/5" — last evaluation result
  mentor_eval_count: z.number().int().min(0).default(0),
})

export const SkillGraphNodeSchema = z.object({
  userId: z.string(),
  topic: z.string(),                     // e.g. "graphs", "dynamic_programming"
  category: CategorySchema,              // DSA | Cloud | Core | System Design
  required_level: LevelSchema,           // from Goal Knowledge Base
  current_level: LevelSchema,            // updated by evaluations + LC signals
  gap: z.number().min(0).max(100),       // percentage: how far from required_level
  signals: SignalsSchema,
  strong_areas: z.array(z.string()).default([]),  // e.g. ["BFS basics", "DFS"]
  weak_areas: z.array(z.string()).default([]),    // e.g. ["Dijkstra", "union-find"]
  last_studied: z.string().datetime().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
})

export type SkillGraphNode = z.infer<typeof SkillGraphNodeSchema>
export type Signals = z.infer<typeof SignalsSchema>

// Schema for the update written by EvaluationService after a verdict
export const SkillGraphUpdateSchema = z.object({
  topic: z.string(),
  new_level: LevelSchema,
  gap: z.number().min(0).max(100),
  strong_areas: z.array(z.string()).optional(),
  weak_areas: z.array(z.string()).optional(),
  eval_score: z.string().optional(),     // e.g. "3/5"
})

export type SkillGraphUpdate = z.infer<typeof SkillGraphUpdateSchema>

// Schema for the tool_use block Claude emits — validated by StreamParser
export const SkillUpdateToolSchema = z.object({
  topic: z.string(),
  new_level: LevelSchema,
  gap: z.number().min(0).max(100),
  weak_areas: z.array(z.string()).default([]),
  strong_areas: z.array(z.string()).default([]),
})

export type SkillUpdateTool = z.infer<typeof SkillUpdateToolSchema>
