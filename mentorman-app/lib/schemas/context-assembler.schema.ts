import { z } from 'zod'
import { CoreProfileSchema } from './core-profile.schema'
import { SkillGraphNodeSchema } from './skill-graph.schema'
import { MessageSchema } from './session.schema'
import { SessionModeSchema } from './shared.schema'

// ─── Context Assembler ────────────────────────────────────────────────────────
// This is the contract between the ContextAssembler and SessionService.
// Every assembler implementation must return an object that satisfies
// AssembledContextSchema — validated at runtime before the LLM call.

// Episodic memory chunk — retrieved from Vector DB
export const EpisodeSchema = z.object({
  id: z.string(),
  text: z.string(),                      // chunk text
  source: z.enum(['session_summary', 'doubt', 'resume']),
  topic: z.string().optional(),
  sessionId: z.string().optional(),
  score: z.number().min(0).max(1),       // similarity score from retrieval
  createdAt: z.string().datetime(),
})

export type Episode = z.infer<typeof EpisodeSchema>

// Input passed to assembler.assemble()
export const SessionInputSchema = z.object({
  userId: z.string(),
  sessionId: z.string(),
  currentTopic: z.string(),
  currentMode: SessionModeSchema,
  conversationWindow: z.array(MessageSchema),
})

export type SessionInput = z.infer<typeof SessionInputSchema>

// ImmediateContext block — uploaded file content available mid-session
export const ImmediateContextBlockSchema = z.object({
  filename: z.string(),
  uploadTimestamp: z.string(),           // ISO date string
  content: z.string(),
  accompanyingMessage: z.string(),
})

export type ImmediateContextBlock = z.infer<typeof ImmediateContextBlockSchema>

// Output returned by every assembler — the LLM prompt contract
export const AssembledContextSchema = z.object({
  systemPrompt: z.string().min(1),
  coreProfile: CoreProfileSchema,
  skillGraphNodes: z.array(SkillGraphNodeSchema),
  episodes: z.array(EpisodeSchema),
  conversationWindow: z.array(MessageSchema),
  // ImmediateContext — uploaded file content (between Skill Graph and Episodic RAG)
  immediateContextBlocks: z.array(ImmediateContextBlockSchema).default([]),
  // metadata for logging / debugging
  meta: z.object({
    assemblerType: z.string(),           // e.g. "SemanticAssembler"
    retrievalLatencyMs: z.number().optional(),
    episodeCount: z.number().int().min(0),
    promptVersion: z.string(),           // e.g. "topic.v1"
    immediateContextCount: z.number().int().min(0).default(0),
  }),
})

export type AssembledContext = z.infer<typeof AssembledContextSchema>
