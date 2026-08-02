/**
 * Topic-based conversation data models and Zod schemas.
 *
 * These interfaces and schemas define the core data structures for the
 * topic conversations + compaction system. They match the design document
 * data models and provide runtime validation via Zod.
 *
 * Requirements: 1.4, 4.1, 7.4, 7.5, 13.1, 13.2
 */

import { z } from 'zod';

// ─── Enums / Literals ─────────────────────────────────────────────────────────

export const TopicStatus = z.enum(['active', 'archived']);
export type TopicStatus = z.infer<typeof TopicStatus>;

export const MessageRole = z.enum(['user', 'assistant']);
export type MessageRole = z.infer<typeof MessageRole>;

// ─── Message Schema & Interface ───────────────────────────────────────────────

export const MessageSchema = z.object({
  type: z.literal('message'),
  id: z.string().uuid(),
  role: MessageRole,
  content: z.string().min(1).max(50_000),
  timestamp: z.coerce.date(),
  tokenCount: z.number().int().nonnegative(),
});

export type Message = z.infer<typeof MessageSchema>;

// ─── SummaryBlock Schema & Interface ──────────────────────────────────────────

export const SummaryBlockSchema = z.object({
  type: z.literal('summary'),
  id: z.string().uuid(),
  summary: z.string().min(1),
  compactedMessageIds: z.array(z.string().uuid()).min(1),
  compactedRange: z.object({
    from: z.coerce.date(),
    to: z.coerce.date(),
  }),
  messageCount: z.number().int().positive(),
  tokenCount: z.number().int().nonnegative(),
  createdAt: z.coerce.date(),
  compactionEventId: z.string(),
});

export type SummaryBlock = z.infer<typeof SummaryBlockSchema>;

// ─── Thread Entry (discriminated union) ───────────────────────────────────────

export const ThreadEntrySchema = z.discriminatedUnion('type', [
  MessageSchema,
  SummaryBlockSchema,
]);

export type ThreadEntry = z.infer<typeof ThreadEntrySchema>;

// ─── Topic Metadata ───────────────────────────────────────────────────────────

export const TopicMetadataSchema = z.object({
  totalMessageCount: z.number().int().nonnegative(),
  currentTokenEstimate: z.number().int().nonnegative(),
});

export type TopicMetadata = z.infer<typeof TopicMetadataSchema>;

// ─── Topic Schema & Interface ─────────────────────────────────────────────────

export const TopicSchema = z.object({
  _id: z.any().optional(), // MongoDB ObjectId — validated at DB layer
  topicId: z.string().uuid(),
  userId: z.string().min(1),
  title: z
    .string()
    .min(1, 'Title must be at least 1 character')
    .max(100, 'Title must be at most 100 characters')
    .transform((val) => val.trim())
    .pipe(z.string().min(1, 'Title must not be empty after trimming')),
  status: TopicStatus,
  mode: z.string().nullable(),
  createdAt: z.coerce.date(),
  lastActiveAt: z.coerce.date(),
  messages: z.array(ThreadEntrySchema),
  compactionCount: z.number().int().nonnegative(),
  metadata: TopicMetadataSchema,
  /** Optimistic concurrency control — incremented on each successful write, reject if stale */
  version: z.number().int().nonnegative().default(0),
});

export type Topic = z.infer<typeof TopicSchema>;

// ─── Title Validation (standalone, for reuse in create/rename) ────────────────

/**
 * Validates a topic title: 1–100 characters after trim, non-empty.
 * Requirement 1.4
 */
export const TopicTitleSchema = z
  .string()
  .min(1, 'Title must be at least 1 character')
  .max(100, 'Title must be at most 100 characters')
  .transform((val) => val.trim())
  .pipe(z.string().min(1, 'Title must not be empty after trimming'));

// ─── Skill Update (referenced by CompactionEvent) ─────────────────────────────

export interface SkillUpdate {
  topic: string;
  newLevel: string;
  gap: number;
  weakAreas: string[];
  strongAreas: string[];
}

// ─── CompactionEvent Interface ────────────────────────────────────────────────

export interface CompactionEvent {
  _id?: unknown; // MongoDB ObjectId
  eventId: string;
  topicId: string;
  userId: string;
  timestamp: Date;
  messagesCompacted: number;
  tokensBeforeCompaction: number;
  tokensAfterCompaction: number;
  tokensReclaimed: number;
  skillUpdateGenerated: boolean;
  skillUpdate: SkillUpdate | null;
  summaryBlockId: string;
}

// ─── TopicListItem Interface ──────────────────────────────────────────────────

export interface TopicListItem {
  topicId: string;
  title: string;
  subject?: string | null; // user-assigned group; absent/"" = Ungrouped
  status: TopicStatus;
  lastActiveAt: Date;
  mode: string | null;
  messagePreview: string; // last message snippet for sidebar
}

// ─── CompactionResult Interface ───────────────────────────────────────────────

export interface CompactionResult {
  summaryBlock: SummaryBlock;
  skillUpdate: SkillUpdate | null;
  messagesCompacted: number;
  tokensReclaimed: number;
}

// ─── CompactionConfig Interface ───────────────────────────────────────────────

export const CompactionConfigSchema = z.object({
  /** Compaction threshold as a percentage (30–90%, default 60%) */
  threshold: z.number().min(30).max(90).default(60),
  /** Total context window budget in tokens (default 200,000) */
  totalBudget: z.number().int().positive().default(200_000),
  /** Maximum summary size as a ratio of compacted tokens (max 25%) */
  maxSummaryRatio: z.number().min(0).max(0.25).default(0.25),
});

export type CompactionConfig = z.infer<typeof CompactionConfigSchema>;
