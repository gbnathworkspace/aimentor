import { describe, it, expect } from 'vitest'
import {
  truncateToTokenLimit,
  summarizeLeetCodeStats,
} from '@/lib/ingestion/session-context-injector'
import type { LeetCodeTopicStats } from '@/lib/schemas'

describe('truncateToTokenLimit', () => {
  it('returns text unchanged when under token limit', () => {
    const shortText = 'Hello world. This is a short sentence.'
    const result = truncateToTokenLimit(shortText)
    expect(result.content).toBe(shortText)
    expect(result.tokenCount).toBeLessThanOrEqual(4000)
  })

  it('truncates long text at sentence boundaries', () => {
    // Generate text that exceeds 4000 tokens (average token ~ 4 chars)
    const sentences = Array.from({ length: 500 }, (_, i) =>
      `This is sentence number ${i + 1} which contains some text to fill up the token budget.`
    )
    const longText = sentences.join(' ')
    const result = truncateToTokenLimit(longText)

    expect(result.tokenCount).toBeLessThanOrEqual(4000)
    // Should end at a sentence boundary (period)
    expect(result.content.trimEnd()).toMatch(/[.!?]$/)
    // Should be shorter than the original
    expect(result.content.length).toBeLessThan(longText.length)
  })

  it('respects custom token limit', () => {
    const text = 'First sentence. Second sentence. Third sentence. Fourth sentence.'
    const result = truncateToTokenLimit(text, 5)

    expect(result.tokenCount).toBeLessThanOrEqual(5)
  })

  it('handles text with different sentence terminators', () => {
    const text = 'Is this a question? Yes it is! This is a statement. ' +
      Array.from({ length: 500 }, () => 'More text to exceed the limit.').join(' ')
    const result = truncateToTokenLimit(text)

    expect(result.tokenCount).toBeLessThanOrEqual(4000)
    expect(result.content.trimEnd()).toMatch(/[.!?]$/)
  })

  it('handles empty text', () => {
    const result = truncateToTokenLimit('')
    expect(result.content).toBe('')
    expect(result.tokenCount).toBe(0)
  })
})

describe('summarizeLeetCodeStats', () => {
  it('generates correct summary for a single topic', () => {
    const stats: LeetCodeTopicStats[] = [
      { topic: 'Arrays', easy: 12, medium: 5, hard: 1, total: 18 },
    ]
    const summary = summarizeLeetCodeStats(stats)
    expect(summary).toBe(
      'LeetCode Summary:\n- Arrays: 12 easy, 5 medium, 1 hard (18 total)'
    )
  })

  it('generates correct summary for multiple topics', () => {
    const stats: LeetCodeTopicStats[] = [
      { topic: 'Arrays', easy: 12, medium: 5, hard: 1, total: 18 },
      { topic: 'Graphs', easy: 4, medium: 2, hard: 0, total: 6 },
    ]
    const summary = summarizeLeetCodeStats(stats)
    expect(summary).toBe(
      'LeetCode Summary:\n' +
      '- Arrays: 12 easy, 5 medium, 1 hard (18 total)\n' +
      '- Graphs: 4 easy, 2 medium, 0 hard (6 total)'
    )
  })

  it('handles topics with zero counts', () => {
    const stats: LeetCodeTopicStats[] = [
      { topic: 'Dynamic Programming', easy: 0, medium: 0, hard: 0, total: 0 },
    ]
    const summary = summarizeLeetCodeStats(stats)
    expect(summary).toBe(
      'LeetCode Summary:\n- Dynamic Programming: 0 easy, 0 medium, 0 hard (0 total)'
    )
  })

  it('handles empty stats array', () => {
    const stats: LeetCodeTopicStats[] = []
    const summary = summarizeLeetCodeStats(stats)
    expect(summary).toBe('LeetCode Summary:\n')
  })

  it('preserves topic names exactly as provided', () => {
    const stats: LeetCodeTopicStats[] = [
      { topic: 'Two Pointers', easy: 3, medium: 7, hard: 2, total: 12 },
      { topic: 'sliding-window', easy: 1, medium: 4, hard: 0, total: 5 },
    ]
    const summary = summarizeLeetCodeStats(stats)
    expect(summary).toContain('- Two Pointers:')
    expect(summary).toContain('- sliding-window:')
  })
})
