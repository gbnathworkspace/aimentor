import { encodingForModel } from 'js-tiktoken'
import type { ImmediateContextDoc } from './types'

// ─── Token Budget Priority ────────────────────────────────────────────────────
// Ensures the assembled context fits within the configured token budget.
// Priority order: Core Profile > Skill Graph > ImmediateContext > Episodic RAG
//
// When the combined context exceeds budget:
// 1. Core Profile and Skill Graph are NEVER dropped
// 2. ImmediateContext blocks are dropped oldest-first (first in the sorted array)
// 3. Final assembled context must fit within the configured token budget
//
// Requirements: 4.4, 4.5
// Property 9: Token budget priority drops ImmediateContext before core context

// ─── Configuration ────────────────────────────────────────────────────────────

/**
 * Default token budget for the full context window sent to the LLM.
 * This covers: system prompt (Core Profile + Skill Graph) + ImmediateContext + Episodic RAG.
 * Can be overridden via CONTEXT_TOKEN_BUDGET environment variable.
 *
 * Claude Sonnet has a 200k context window, but we use a conservative budget
 * to leave room for the conversation window and LLM response.
 */
export const DEFAULT_TOKEN_BUDGET = 16_000

const TOKENIZER_MODEL = 'gpt-4' // uses cl100k_base encoding

/**
 * Returns the configured token budget from environment or the default.
 */
export function getTokenBudget(): number {
  const envBudget = process.env.CONTEXT_TOKEN_BUDGET
  if (envBudget) {
    const parsed = parseInt(envBudget, 10)
    if (!isNaN(parsed) && parsed > 0) return parsed
  }
  return DEFAULT_TOKEN_BUDGET
}

// ─── Token Counting ───────────────────────────────────────────────────────────

/**
 * Counts the number of tokens in a text string using the cl100k_base tokenizer.
 */
export function countTokens(text: string): number {
  if (!text) return 0
  const enc = encodingForModel(TOKENIZER_MODEL)
  return enc.encode(text).length
}

// ─── Budget Priority Logic ────────────────────────────────────────────────────

export interface ContextTokenCounts {
  /** Tokens in the system prompt (Core Profile + Skill Graph) — never dropped */
  coreContextTokens: number
  /** Tokens in Episodic RAG results */
  episodicRagTokens: number
}

export interface BudgetPriorityResult {
  /** ImmediateContext docs that fit within budget (may be a subset of input) */
  includedDocs: ImmediateContextDoc[]
  /** ImmediateContext docs that were dropped to fit budget */
  droppedDocs: ImmediateContextDoc[]
  /** Total tokens of included ImmediateContext */
  includedTokens: number
  /** Whether any docs were dropped */
  budgetExceeded: boolean
}

/**
 * Applies token budget priority logic to ImmediateContext blocks.
 *
 * Given the token counts for core context (Core Profile + Skill Graph) and
 * episodic RAG, determines which ImmediateContext documents can fit within
 * the token budget.
 *
 * Rules:
 * - Core Profile and Skill Graph tokens are NEVER dropped (always included)
 * - Episodic RAG tokens are included in the base budget calculation
 * - ImmediateContext blocks are dropped oldest-first (docs[0] is dropped first)
 *   until the total fits within the budget
 *
 * @param docs - ImmediateContext documents sorted by createdAt ascending (oldest first)
 * @param contextTokenCounts - Token counts for non-ImmediateContext context parts
 * @param tokenBudget - Maximum allowed total tokens (defaults to configured budget)
 */
export function applyTokenBudgetPriority(
  docs: ImmediateContextDoc[],
  contextTokenCounts: ContextTokenCounts,
  tokenBudget?: number,
): BudgetPriorityResult {
  const budget = tokenBudget ?? getTokenBudget()

  if (docs.length === 0) {
    return {
      includedDocs: [],
      droppedDocs: [],
      includedTokens: 0,
      budgetExceeded: false,
    }
  }

  const { coreContextTokens, episodicRagTokens } = contextTokenCounts

  // Base tokens that are always present (core context + episodic RAG)
  const baseTokens = coreContextTokens + episodicRagTokens

  // Total ImmediateContext tokens
  const totalImmediateTokens = docs.reduce((sum, doc) => sum + doc.tokenCount, 0)

  // Check if everything fits
  const totalTokens = baseTokens + totalImmediateTokens
  if (totalTokens <= budget) {
    return {
      includedDocs: [...docs],
      droppedDocs: [],
      includedTokens: totalImmediateTokens,
      budgetExceeded: false,
    }
  }

  // Budget exceeded — drop ImmediateContext blocks oldest-first
  // Available budget for ImmediateContext = total budget - base tokens
  const availableForImmediate = Math.max(0, budget - baseTokens)

  // If no room at all for ImmediateContext, drop everything
  if (availableForImmediate <= 0) {
    return {
      includedDocs: [],
      droppedDocs: [...docs],
      includedTokens: 0,
      budgetExceeded: true,
    }
  }

  // Greedily include docs from newest to oldest (reverse order) since we
  // drop oldest-first. This means we keep the newest docs.
  // Strategy: iterate from the end (newest) and include while within budget.
  const included: ImmediateContextDoc[] = []
  let usedTokens = 0

  for (let i = docs.length - 1; i >= 0; i--) {
    const doc = docs[i]
    if (usedTokens + doc.tokenCount <= availableForImmediate) {
      included.unshift(doc) // maintain chronological order
      usedTokens += doc.tokenCount
    }
    // If adding this doc would exceed budget, skip it (it gets dropped)
  }

  // Everything not included was dropped
  const includedJobIds = new Set(included.map(d => d.jobId))
  const dropped = docs.filter(d => !includedJobIds.has(d.jobId))

  return {
    includedDocs: included,
    droppedDocs: dropped,
    includedTokens: usedTokens,
    budgetExceeded: true,
  }
}
