import { describe, it, expect } from 'vitest'
import {
  assembleContext,
  SKIPPED_ONBOARDING_ADDENDUM,
  CONVERSATION_WINDOW_SIZE,
} from '@/lib/context-assembler/assemble-context'
import type { CoreProfile, SkillGraphNode, Episode, Message } from '@/lib/schemas'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeProfile(overrides: Partial<CoreProfile> = {}): CoreProfile {
  return {
    userId: 'user-1',
    goal: 'Learn DSA',
    deadline: '2025-06-01',
    overall_level: 'intermediate',
    daily_availability: '2 hours',
    email: 'test@test.com',
    profile_status: 'complete',
    ...overrides,
  }
}

function makeSkippedProfile(overrides: Partial<CoreProfile> = {}): CoreProfile {
  return makeProfile({
    goal: 'exploring',
    deadline: null,
    overall_level: 'beginner',
    daily_availability: '1 hour',
    profile_status: 'skipped',
    ...overrides,
  })
}

function makeSkillNode(topic: string): SkillGraphNode {
  return {
    userId: 'user-1',
    topic,
    category: 'DSA',
    current_level: 'novice',
    required_level: 'medium',
    gap: 40,
    strong_areas: [],
    weak_areas: ['recursion'],
    signals: { mentor_eval_count: 0 },
  } as SkillGraphNode
}

function makeEpisode(id: string): Episode {
  return {
    id,
    text: `Episode ${id} text content`,
    source: 'session_summary',
    topic: 'graphs',
    score: 0.85,
    createdAt: new Date().toISOString(),
  }
}

function makeMessage(role: 'user' | 'mentor', content: string): Message {
  return {
    id: `msg-${Math.random().toString(36).slice(2)}`,
    role,
    content,
    timestamp: new Date().toISOString(),
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('assembleContext', () => {
  describe('when profile_status is "skipped"', () => {
    it('includes the skipped-onboarding addendum', () => {
      const result = assembleContext({
        coreProfile: makeSkippedProfile(),
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.addendum).toBe(SKIPPED_ONBOARDING_ADDENDUM)
    })

    it('omits Skill Graph layer entirely', () => {
      const result = assembleContext({
        coreProfile: makeSkippedProfile(),
        skillGraphNodes: [makeSkillNode('graphs'), makeSkillNode('trees')],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.promptInput.skillGraphNodes).toEqual([])
      expect(result.skillGraphIncluded).toBe(false)
    })

    it('omits Episodic Memory layer entirely', () => {
      const result = assembleContext({
        coreProfile: makeSkippedProfile(),
        skillGraphNodes: [],
        episodes: [makeEpisode('ep1'), makeEpisode('ep2')],
        conversationWindow: [],
      })

      expect(result.promptInput.episodes).toEqual([])
      expect(result.episodicMemoryIncluded).toBe(false)
    })

    it('includes the conversation window', () => {
      const messages = [
        makeMessage('user', 'Hello'),
        makeMessage('mentor', 'Hi there!'),
      ]

      const result = assembleContext({
        coreProfile: makeSkippedProfile(),
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: messages,
      })

      expect(result.promptInput.conversationWindow).toEqual(messages)
    })
  })

  describe('when profile is null (no profile exists)', () => {
    it('includes the addendum', () => {
      const result = assembleContext({
        coreProfile: null,
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.addendum).toBe(SKIPPED_ONBOARDING_ADDENDUM)
    })

    it('omits Skill Graph and Episodic Memory', () => {
      const result = assembleContext({
        coreProfile: null,
        skillGraphNodes: [makeSkillNode('arrays')],
        episodes: [makeEpisode('ep1')],
        conversationWindow: [],
      })

      expect(result.promptInput.skillGraphNodes).toEqual([])
      expect(result.promptInput.episodes).toEqual([])
      expect(result.skillGraphIncluded).toBe(false)
      expect(result.episodicMemoryIncluded).toBe(false)
    })

    it('provides a safe profile with empty/default fields', () => {
      const result = assembleContext({
        coreProfile: null,
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.promptInput.coreProfile.profile_status).toBe('skipped')
      expect(result.promptInput.coreProfile.goal).toBe('')
      expect(result.promptInput.coreProfile.deadline).toBeNull()
      expect(result.promptInput.coreProfile.daily_availability).toBe('')
    })

    it('assembles with only system prompt + addendum + conversation window', () => {
      const messages = [
        makeMessage('user', 'What is a binary tree?'),
        makeMessage('mentor', 'A binary tree is a data structure...'),
      ]

      const result = assembleContext({
        coreProfile: null,
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: messages,
      })

      expect(result.addendum).toBe(SKIPPED_ONBOARDING_ADDENDUM)
      expect(result.promptInput.conversationWindow).toEqual(messages)
      expect(result.promptInput.skillGraphNodes).toEqual([])
      expect(result.promptInput.episodes).toEqual([])
    })

    it('never throws an error', () => {
      expect(() =>
        assembleContext({
          coreProfile: null,
          skillGraphNodes: [],
          episodes: [],
          conversationWindow: [],
        }),
      ).not.toThrow()
    })
  })

  describe('when Core Profile fields are missing/null', () => {
    it('handles null deadline gracefully', () => {
      const result = assembleContext({
        coreProfile: makeProfile({ deadline: null }),
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.promptInput.coreProfile.deadline).toBeNull()
    })

    it('handles missing goal gracefully (empty string)', () => {
      const profileWithoutGoal = makeProfile()
      ;(profileWithoutGoal as any).goal = undefined

      const result = assembleContext({
        coreProfile: profileWithoutGoal,
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.promptInput.coreProfile.goal).toBe('')
    })

    it('handles missing daily_availability gracefully', () => {
      const profileMissingAvailability = makeProfile()
      ;(profileMissingAvailability as any).daily_availability = undefined

      const result = assembleContext({
        coreProfile: profileMissingAvailability,
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.promptInput.coreProfile.daily_availability).toBe('')
    })

    it('handles all fields missing without erroring', () => {
      const emptyProfile = {
        userId: 'user-1',
        goal: undefined,
        deadline: undefined,
        overall_level: undefined,
        daily_availability: undefined,
        email: undefined,
        profile_status: 'complete' as const,
      }

      expect(() =>
        assembleContext({
          coreProfile: emptyProfile as any,
          skillGraphNodes: [],
          episodes: [],
          conversationWindow: [],
        }),
      ).not.toThrow()
    })
  })

  describe('when profile_status is "complete"', () => {
    it('does not include the addendum', () => {
      const result = assembleContext({
        coreProfile: makeProfile(),
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: [],
      })

      expect(result.addendum).toBeNull()
    })

    it('includes Skill Graph nodes', () => {
      const nodes = [makeSkillNode('graphs'), makeSkillNode('dp')]

      const result = assembleContext({
        coreProfile: makeProfile(),
        skillGraphNodes: nodes,
        episodes: [],
        conversationWindow: [],
      })

      expect(result.promptInput.skillGraphNodes).toEqual(nodes)
      expect(result.skillGraphIncluded).toBe(true)
    })

    it('includes Episodic Memory', () => {
      const episodes = [makeEpisode('ep1')]

      const result = assembleContext({
        coreProfile: makeProfile(),
        skillGraphNodes: [],
        episodes,
        conversationWindow: [],
      })

      expect(result.promptInput.episodes).toEqual(episodes)
      expect(result.episodicMemoryIncluded).toBe(true)
    })
  })

  describe('conversation window trimming', () => {
    it('trims conversation window to last 6 turns', () => {
      const messages = Array.from({ length: 10 }, (_, i) =>
        makeMessage(i % 2 === 0 ? 'user' : 'mentor', `Message ${i}`),
      )

      const result = assembleContext({
        coreProfile: makeSkippedProfile(),
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: messages,
      })

      expect(result.promptInput.conversationWindow).toHaveLength(CONVERSATION_WINDOW_SIZE)
      // Should be the last 6 messages
      expect(result.promptInput.conversationWindow[0].content).toBe('Message 4')
      expect(result.promptInput.conversationWindow[5].content).toBe('Message 9')
    })

    it('keeps all messages when fewer than 6 exist', () => {
      const messages = [
        makeMessage('user', 'Hello'),
        makeMessage('mentor', 'Hi!'),
      ]

      const result = assembleContext({
        coreProfile: makeSkippedProfile(),
        skillGraphNodes: [],
        episodes: [],
        conversationWindow: messages,
      })

      expect(result.promptInput.conversationWindow).toHaveLength(2)
    })
  })
})
