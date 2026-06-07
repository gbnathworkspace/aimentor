import { ImmediateContextRepo } from './immediate-context.repo'
import { applyTokenBudgetPriority, type ContextTokenCounts } from './token-budget'
import type { ImmediateContextBlock, ImmediateContextDoc } from './types'

// ─── ImmediateContext Assembler ───────────────────────────────────────────────
// Handles the assembly of ImmediateContext blocks into the LLM context.
// This module provides:
// 1. Fetching and formatting ImmediateContext blocks
// 2. Relative time formatting for upload timestamps
// 3. System instruction generation for active uploaded files
// 4. Token budget priority logic (drops ImmediateContext oldest-first when over budget)
//
// Assembly position: between Skill Graph nodes and Episodic RAG results
// Priority: Core Profile > Skill Graph > ImmediateContext > Episodic RAG

/**
 * Formats a Date into a human-readable relative time string.
 * Examples: "just now", "2 minutes ago", "1 hour ago", "3 hours ago"
 */
export function formatRelativeTime(date: Date, now: Date = new Date()): string {
  const diffMs = now.getTime() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) return 'just now'
  if (diffMinutes === 1) return '1 minute ago'
  if (diffMinutes < 60) return `${diffMinutes} minutes ago`
  if (diffHours === 1) return '1 hour ago'
  if (diffHours < 24) return `${diffHours} hours ago`
  if (diffDays === 1) return '1 day ago'
  return `${diffDays} days ago`
}

/**
 * Formats a single ImmediateContext document into a labeled context block string.
 * Format: [File: {filename}, uploaded {relative time}]
 */
export function formatImmediateContextLabel(filename: string, createdAt: Date, now?: Date): string {
  return `[File: ${filename}, uploaded ${formatRelativeTime(createdAt, now)}]`
}

/**
 * Converts raw ImmediateContext documents into structured blocks for assembly.
 * Documents must already be sorted by createdAt ascending.
 */
export function buildImmediateContextBlocks(docs: ImmediateContextDoc[]): ImmediateContextBlock[] {
  return docs.map(doc => ({
    filename: doc.filename,
    uploadTimestamp: doc.createdAt.toISOString(),
    content: doc.content,
    accompanyingMessage: doc.accompanyingMessage,
  }))
}

/**
 * Formats ImmediateContext blocks into the text that gets inserted into the LLM context.
 * Each block is labeled with filename and relative upload time.
 * Blocks are separated by double newlines.
 */
export function formatImmediateContextForPrompt(
  docs: ImmediateContextDoc[],
  now: Date = new Date()
): string {
  if (docs.length === 0) return ''

  const sections = docs.map(doc => {
    const label = formatImmediateContextLabel(doc.filename, doc.createdAt, now)
    const parts = [label]
    if (doc.accompanyingMessage) {
      parts.push(`User note: ${doc.accompanyingMessage}`)
    }
    parts.push(doc.content)
    return parts.join('\n')
  })

  return sections.join('\n\n')
}

/**
 * Generates the system instruction that informs the LLM about active uploaded files.
 * Returns null if no active ImmediateContext documents exist.
 *
 * This instruction is included when any ImmediateContext is present and removed
 * when all ImmediateContext documents become inactive.
 */
export function buildUploadSystemInstruction(docs: ImmediateContextDoc[]): string | null {
  if (docs.length === 0) return null

  const fileList = docs.map(doc => {
    const parts = [`- ${doc.filename} (${doc.fileType})`]
    if (doc.accompanyingMessage) {
      parts[0] += `: "${doc.accompanyingMessage}"`
    }
    return parts[0]
  })

  return `The user has uploaded the following file(s) during this session. Their content is included below as context blocks labeled with [File: ...]. Reference these files by name when relevant to the conversation.

Active uploaded files:
${fileList.join('\n')}`
}

/**
 * Options for assembleImmediateContext to enable token budget enforcement.
 * When contextTokenCounts is provided, the assembler applies budget priority
 * logic — dropping ImmediateContext blocks oldest-first to fit within budget.
 */
export interface AssembleImmediateContextOptions {
  /** Token counts for Core Profile + Skill Graph and Episodic RAG.
   *  When provided, enables token budget enforcement. */
  contextTokenCounts?: ContextTokenCounts
  /** Override the default token budget (for testing or per-call configuration) */
  tokenBudget?: number
}

/**
 * Main assembly function: fetches active ImmediateContext for a session and
 * returns all data needed by the ContextAssembler to include it in the LLM call.
 *
 * When contextTokenCounts is provided, applies token budget priority:
 * - Core Profile and Skill Graph are never dropped
 * - ImmediateContext blocks are dropped oldest-first until within budget
 *
 * Returns:
 * - blocks: structured ImmediateContextBlock[] for the AssembledContext
 * - formattedText: the text to insert between Skill Graph and Episodic RAG
 * - systemInstruction: the system instruction to include, or null if no active context
 * - totalTokens: total token count of included ImmediateContext
 * - droppedCount: number of ImmediateContext blocks dropped due to budget
 */
export async function assembleImmediateContext(
  sessionId: string,
  options?: AssembleImmediateContextOptions,
): Promise<{
  blocks: ImmediateContextBlock[]
  formattedText: string
  systemInstruction: string | null
  totalTokens: number
  droppedCount: number
}> {
  const docs = await ImmediateContextRepo.getActiveForSession(sessionId)

  if (docs.length === 0) {
    return {
      blocks: [],
      formattedText: '',
      systemInstruction: null,
      totalTokens: 0,
      droppedCount: 0,
    }
  }

  // Apply token budget priority if context counts are provided
  let includedDocs: ImmediateContextDoc[]
  let droppedCount: number

  if (options?.contextTokenCounts) {
    const result = applyTokenBudgetPriority(
      docs,
      options.contextTokenCounts,
      options.tokenBudget,
    )
    includedDocs = result.includedDocs
    droppedCount = result.droppedDocs.length
  } else {
    includedDocs = docs
    droppedCount = 0
  }

  if (includedDocs.length === 0) {
    return {
      blocks: [],
      formattedText: '',
      systemInstruction: null,
      totalTokens: 0,
      droppedCount,
    }
  }

  const now = new Date()
  const blocks = buildImmediateContextBlocks(includedDocs)
  const formattedText = formatImmediateContextForPrompt(includedDocs, now)
  const systemInstruction = buildUploadSystemInstruction(includedDocs)
  const totalTokens = includedDocs.reduce((sum, doc) => sum + doc.tokenCount, 0)

  return {
    blocks,
    formattedText,
    systemInstruction,
    totalTokens,
    droppedCount,
  }
}
