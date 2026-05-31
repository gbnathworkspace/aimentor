import { z } from 'zod'
import { LevelSchema } from './shared.schema'

// ─── Stream Events ────────────────────────────────────────────────────────────
// Typed SSE events emitted by StreamParser and consumed by useStream() hook.
// This is the client/server contract for the streaming chat interface.

export const TokenEventSchema = z.object({
  type: z.literal('token'),
  data: z.object({
    text: z.string(),
  }),
})

export const NudgeEventSchema = z.object({
  type: z.literal('nudge'),
  data: z.object({
    message: z.string(),
    pinTopic: z.string(),
  }),
})

export const SkillUpdateEventSchema = z.object({
  type: z.literal('skill_update'),
  data: z.object({
    topic: z.string(),
    newLevel: LevelSchema,
    gap: z.number().min(0).max(100),
    weakAreas: z.array(z.string()).default([]),
    strongAreas: z.array(z.string()).default([]),
  }),
})

export const DoneEventSchema = z.object({
  type: z.literal('done'),
  data: z.object({
    sessionId: z.string(),
    messageCount: z.number().int().min(0),
  }),
})

export const ErrorEventSchema = z.object({
  type: z.literal('error'),
  data: z.object({
    message: z.string(),
    retryable: z.boolean(),
  }),
})

// Discriminated union — parse with StreamEventSchema.parse(raw)
export const StreamEventSchema = z.discriminatedUnion('type', [
  TokenEventSchema,
  NudgeEventSchema,
  SkillUpdateEventSchema,
  DoneEventSchema,
  ErrorEventSchema,
])

export type StreamEvent = z.infer<typeof StreamEventSchema>
export type TokenEvent = z.infer<typeof TokenEventSchema>
export type NudgeEvent = z.infer<typeof NudgeEventSchema>
export type SkillUpdateEvent = z.infer<typeof SkillUpdateEventSchema>
export type DoneEvent = z.infer<typeof DoneEventSchema>
export type ErrorEvent = z.infer<typeof ErrorEventSchema>

// Helper — formats a StreamEvent as an SSE string
export function toSSEString(event: StreamEvent): string {
  return `event: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`
}
