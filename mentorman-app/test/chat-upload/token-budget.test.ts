import { describe, it, expect } from 'vitest'
import {
  applyTokenBudgetPriority,
  countTokens,
  getTokenBudget,
  DEFAULT_TOKEN_BUDGET,
} from '@/lib/context-assembler/token-budget'
import type { ImmediateContextDoc } from '@/lib/context-assembler/types'

// ─── Helper: create mock ImmediateContextDoc ──────────────────────────────────
function makeDoc(overrides: Partial<ImmediateContextDoc> & { tokenCount: number; createdAt: Date }): ImmediateContextDoc {
  return {
    sessionId: 'session-1',
    userId: 'user-1',
    jobId: `job-${overrides.createdAt.getTime()}`,
    filename: `file-${overrides.createdAt.getTime()}.pdf`,
    fileType: 'resume',
    content: 'test content',
    accompanyingMessage: '',
    active: true,
    updatedAt: overrides.createdAt,
    ...overrides,
  }
}

describe('getTokenBudget', () => {
  it('returns DEFAULT_TOKEN_BUDGET when env var is not set', () => {
    const original = process.env.CONTEXT_TOKEN_BUDGET
    delete process.env.CONTEXT_TOKEN_BUDGET
    expect(getTokenBudget()).toBe(DEFAULT_TOKEN_BUDGET)
    if (original) process.env.CONTEXT_TOKEN_BUDGET = original
  })

  it('returns parsed env var when set', () => {
    const original = process.env.CONTEXT_TOKEN_BUDGET
    process.env.CONTEXT_TOKEN_BUDGET = '20000'
    expect(getTokenBudget()).toBe(20000)
    if (original) {
      process.env.CONTEXT_TOKEN_BUDGET = original
    } else {
      delete process.env.CONTEXT_TOKEN_BUDGET
    }
  })

  it('falls back to default for invalid env var', () => {
    const original = process.env.CONTEXT_TOKEN_BUDGET
    process.env.CONTEXT_TOKEN_BUDGET = 'not-a-number'
    expect(getTokenBudget()).toBe(DEFAULT_TOKEN_BUDGET)
    if (original) {
      process.env.CONTEXT_TOKEN_BUDGET = original
    } else {
      delete process.env.CONTEXT_TOKEN_BUDGET
    }
  })
})

describe('countTokens', () => {
  it('returns 0 for empty string', () => {
    expect(countTokens('')).toBe(0)
  })

  it('counts tokens for a simple string', () => {
    const count = countTokens('Hello world')
    expect(count).toBeGreaterThan(0)
    expect(count).toBeLessThan(10) // "Hello world" is 2 tokens
  })

  it('returns higher count for longer strings', () => {
    const short = countTokens('Hello')
    const long = countTokens('Hello world, this is a much longer string with many more tokens.')
    expect(long).toBeGreaterThan(short)
  })
})

describe('applyTokenBudgetPriority', () => {
  it('returns all docs when total tokens are within budget', () => {
    const docs = [
      makeDoc({ tokenCount: 100, createdAt: new Date('2024-01-01T00:00:00Z') }),
      makeDoc({ tokenCount: 200, createdAt: new Date('2024-01-01T01:00:00Z') }),
    ]

    const result = applyTokenBudgetPriority(
      docs,
      { coreContextTokens: 500, episodicRagTokens: 200 },
      2000, // budget
    )

    expect(result.includedDocs).toHaveLength(2)
    expect(result.droppedDocs).toHaveLength(0)
    expect(result.includedTokens).toBe(300)
    expect(result.budgetExceeded).toBe(false)
  })

  it('drops oldest ImmediateContext blocks first when over budget', () => {
    const oldest = makeDoc({ tokenCount: 500, createdAt: new Date('2024-01-01T00:00:00Z'), jobId: 'job-oldest' })
    const middle = makeDoc({ tokenCount: 500, createdAt: new Date('2024-01-01T01:00:00Z'), jobId: 'job-middle' })
    const newest = makeDoc({ tokenCount: 500, createdAt: new Date('2024-01-01T02:00:00Z'), jobId: 'job-newest' })
    const docs = [oldest, middle, newest]

    // Budget: core=500, episodic=200, budget=1500
    // Available for immediate: 1500 - 500 - 200 = 800
    // Can fit 1 doc (500 tokens), keep newest
    const result = applyTokenBudgetPriority(
      docs,
      { coreContextTokens: 500, episodicRagTokens: 200 },
      1500,
    )

    expect(result.budgetExceeded).toBe(true)
    expect(result.includedDocs).toHaveLength(1)
    expect(result.includedDocs[0].jobId).toBe('job-newest')
    expect(result.droppedDocs).toHaveLength(2)
    expect(result.droppedDocs[0].jobId).toBe('job-oldest')
    expect(result.droppedDocs[1].jobId).toBe('job-middle')
    expect(result.includedTokens).toBe(500)
  })

  it('never drops core context — drops all ImmediateContext if no room', () => {
    const docs = [
      makeDoc({ tokenCount: 500, createdAt: new Date('2024-01-01T00:00:00Z') }),
    ]

    // Core context alone exceeds budget
    const result = applyTokenBudgetPriority(
      docs,
      { coreContextTokens: 1500, episodicRagTokens: 200 },
      1000, // budget is less than core + episodic
    )

    expect(result.budgetExceeded).toBe(true)
    expect(result.includedDocs).toHaveLength(0)
    expect(result.droppedDocs).toHaveLength(1)
    expect(result.includedTokens).toBe(0)
  })

  it('handles empty docs array', () => {
    const result = applyTokenBudgetPriority(
      [],
      { coreContextTokens: 500, episodicRagTokens: 200 },
      1000,
    )

    expect(result.includedDocs).toHaveLength(0)
    expect(result.droppedDocs).toHaveLength(0)
    expect(result.includedTokens).toBe(0)
    expect(result.budgetExceeded).toBe(false)
  })

  it('keeps newest docs and maintains chronological order', () => {
    const doc1 = makeDoc({ tokenCount: 300, createdAt: new Date('2024-01-01T00:00:00Z'), jobId: 'job-1' })
    const doc2 = makeDoc({ tokenCount: 300, createdAt: new Date('2024-01-01T01:00:00Z'), jobId: 'job-2' })
    const doc3 = makeDoc({ tokenCount: 300, createdAt: new Date('2024-01-01T02:00:00Z'), jobId: 'job-3' })
    const doc4 = makeDoc({ tokenCount: 300, createdAt: new Date('2024-01-01T03:00:00Z'), jobId: 'job-4' })
    const docs = [doc1, doc2, doc3, doc4]

    // Budget: core=500, episodic=100, budget=1200
    // Available for immediate: 1200 - 500 - 100 = 600
    // Can fit 2 docs (600 tokens exactly), keep 2 newest
    const result = applyTokenBudgetPriority(
      docs,
      { coreContextTokens: 500, episodicRagTokens: 100 },
      1200,
    )

    expect(result.budgetExceeded).toBe(true)
    expect(result.includedDocs).toHaveLength(2)
    // Should be in chronological order (oldest first among included)
    expect(result.includedDocs[0].jobId).toBe('job-3')
    expect(result.includedDocs[1].jobId).toBe('job-4')
    expect(result.droppedDocs).toHaveLength(2)
    expect(result.includedTokens).toBe(600)
  })

  it('ensures final assembled context fits within token budget', () => {
    const docs = [
      makeDoc({ tokenCount: 1000, createdAt: new Date('2024-01-01T00:00:00Z') }),
      makeDoc({ tokenCount: 1000, createdAt: new Date('2024-01-01T01:00:00Z') }),
      makeDoc({ tokenCount: 1000, createdAt: new Date('2024-01-01T02:00:00Z') }),
    ]

    const coreContextTokens = 5000
    const episodicRagTokens = 2000
    const tokenBudget = 8500

    const result = applyTokenBudgetPriority(
      docs,
      { coreContextTokens, episodicRagTokens },
      tokenBudget,
    )

    // Available for immediate: 8500 - 5000 - 2000 = 1500
    // Can fit 1 doc (1000 tokens), keep newest
    const totalAssembled = coreContextTokens + episodicRagTokens + result.includedTokens
    expect(totalAssembled).toBeLessThanOrEqual(tokenBudget)
    expect(result.includedDocs).toHaveLength(1)
    expect(result.budgetExceeded).toBe(true)
  })

  it('includes docs of varying sizes greedily from newest', () => {
    const docs = [
      makeDoc({ tokenCount: 800, createdAt: new Date('2024-01-01T00:00:00Z'), jobId: 'job-large-old' }),
      makeDoc({ tokenCount: 200, createdAt: new Date('2024-01-01T01:00:00Z'), jobId: 'job-small-mid' }),
      makeDoc({ tokenCount: 300, createdAt: new Date('2024-01-01T02:00:00Z'), jobId: 'job-medium-new' }),
    ]

    // Budget: core=500, episodic=100, budget=1100
    // Available for immediate: 1100 - 500 - 100 = 500
    // Greedy from newest: doc3(300) fits → 300, doc2(200) fits → 500, doc1(800) doesn't fit
    const result = applyTokenBudgetPriority(
      docs,
      { coreContextTokens: 500, episodicRagTokens: 100 },
      1100,
    )

    expect(result.includedDocs).toHaveLength(2)
    expect(result.includedDocs[0].jobId).toBe('job-small-mid')
    expect(result.includedDocs[1].jobId).toBe('job-medium-new')
    expect(result.includedTokens).toBe(500)
    expect(result.droppedDocs).toHaveLength(1)
    expect(result.droppedDocs[0].jobId).toBe('job-large-old')
  })
})
