// ─── Context Assembler ────────────────────────────────────────────────────────
// Public API for the context assembler module.

export type { ImmediateContextBlock, ImmediateContextDoc } from './types'
export { ImmediateContextRepo } from './immediate-context.repo'
export {
  assembleImmediateContext,
  formatRelativeTime,
  formatImmediateContextLabel,
  formatImmediateContextForPrompt,
  buildImmediateContextBlocks,
  buildUploadSystemInstruction,
} from './immediate-context-assembler'
export type { AssembleImmediateContextOptions } from './immediate-context-assembler'
export {
  applyTokenBudgetPriority,
  countTokens,
  getTokenBudget,
  DEFAULT_TOKEN_BUDGET,
} from './token-budget'
export type { ContextTokenCounts, BudgetPriorityResult } from './token-budget'
