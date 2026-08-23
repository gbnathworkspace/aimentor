import { describe, it, expect } from 'vitest';
import { isNearDuplicate, buildGoalCards } from './SubtopicWeightsModal';
import type { CoreProfile } from '@/lib/mentorman-api';

describe('isNearDuplicate', () => {
  it('treats restatements of the same focus area as duplicates', () => {
    expect(
      isNearDuplicate(
        'Enterprise REST API development and system design',
        'Enterprise REST API design and scalability'
      )
    ).toBe(true);
  });

  it('keeps genuinely different areas distinct', () => {
    expect(isNearDuplicate('System design', 'Behavioral interviews')).toBe(false);
    expect(isNearDuplicate('AWS Lambda cold starts', 'Enterprise REST API design')).toBe(false);
  });

  it('does not flag empty/stopword-only strings as duplicates', () => {
    expect(isNearDuplicate('and the', 'for with')).toBe(false);
  });
});

describe('buildGoalCards', () => {
  const profileWith = (p: Partial<CoreProfile>) => p as CoreProfile;

  it('drops near-duplicate focus areas and caps at two', () => {
    const cards = buildGoalCards(
      profileWith({
        focus_areas: [
          'Enterprise REST API development and system design',
          'Enterprise REST API design and scalability',
          'AWS Lambda cold starts',
          'Behavioral interviews',
        ],
      }),
      'AWS CI/CD'
    );
    const focusTitles = cards.filter((c) => c.key.startsWith('focus:')).map((c) => c.title);
    expect(focusTitles).toEqual([
      'Enterprise REST API development and system design',
      'AWS Lambda cold starts',
    ]);
  });

  it('omits per-card descriptions for focus areas so they never repeat a generic line', () => {
    const cards = buildGoalCards(
      profileWith({ focus_areas: ['System design', 'Behavioral interviews'] }),
      'AWS CI/CD'
    );
    const focusCards = cards.filter((c) => c.key.startsWith('focus:'));
    expect(focusCards).toHaveLength(2);
    for (const c of focusCards) expect(c.description).toBeUndefined();
  });

  it('always offers a revise option, even with an empty profile', () => {
    const cards = buildGoalCards(null, 'AWS CI/CD');
    expect(cards.map((c) => c.key)).toEqual(['revise']);
  });

  it('flags focus/context cards as fromL1Scope, but not revise', () => {
    const cards = buildGoalCards(
      profileWith({
        focus_areas: ['System design'],
        learning_context: 'job_interview',
        learning_context_detail: { label: 'FAANG interviews' } as any,
      }),
      'AWS CI/CD'
    );
    const byKey = Object.fromEntries(cards.map((c) => [c.key, c.fromL1Scope]));
    expect(byKey['focus:System design']).toBe(true);
    expect(byKey['context']).toBe(true);
    expect(byKey['revise']).toBeUndefined();
  });

  it('adds a context card only for a non-default learning context', () => {
    expect(
      buildGoalCards(profileWith({ learning_context: 'self_directed' }), 'AWS CI/CD')
        .some((c) => c.key === 'context')
    ).toBe(false);

    const cards = buildGoalCards(profileWith({ learning_context: 'job_interview' }), 'AWS CI/CD');
    const ctx = cards.find((c) => c.key === 'context');
    expect(ctx?.tag).toBe('INTERVIEW');
    expect(ctx?.title).toBe('Job Interview');
  });

  it('drops a focus area l1_scope judged irrelevant to this topic', () => {
    const cards = buildGoalCards(
      profileWith({ focus_areas: ['System design', 'Behavioral interviews'] }),
      'AWS CI/CD',
      [{ situation: 'Behavioral interviews', verdict: 'irrelevant' }]
    );
    const focusTitles = cards.filter((c) => c.key.startsWith('focus:')).map((c) => c.title);
    expect(focusTitles).toEqual(['System design']);
  });

  it('keeps a focus area with no l1_scope verdict yet (unfiltered fallback)', () => {
    const cards = buildGoalCards(
      profileWith({ focus_areas: ['System design'] }),
      'AWS CI/CD',
      []
    );
    expect(cards.some((c) => c.key === 'focus:System design')).toBe(true);
  });

  it('keeps a focus area judged "uncertain" — callers resolve before calling this', () => {
    const cards = buildGoalCards(
      profileWith({ focus_areas: ['System design'] }),
      'AWS CI/CD',
      [{ situation: 'System design', verdict: 'uncertain' }]
    );
    expect(cards.some((c) => c.key === 'focus:System design')).toBe(true);
  });

  it('ranks a "relevant"-judged focus area ahead of an unjudged one, regardless of profile order', () => {
    const cards = buildGoalCards(
      profileWith({ focus_areas: ['Behavioral interviews', 'System design'] }),
      'AWS CI/CD',
      [{ situation: 'System design', verdict: 'relevant' }]
    );
    const focusTitles = cards.filter((c) => c.key.startsWith('focus:')).map((c) => c.title);
    expect(focusTitles).toEqual(['System design', 'Behavioral interviews']);
  });

  it('ranks a "relevant"-judged focus area ahead of an "uncertain" one', () => {
    const cards = buildGoalCards(
      profileWith({ focus_areas: ['Behavioral interviews', 'System design'] }),
      'AWS CI/CD',
      [
        { situation: 'Behavioral interviews', verdict: 'uncertain' },
        { situation: 'System design', verdict: 'relevant' },
      ]
    );
    const focusTitles = cards.filter((c) => c.key.startsWith('focus:')).map((c) => c.title);
    expect(focusTitles).toEqual(['System design', 'Behavioral interviews']);
  });

  it('drops the context card when its label is judged irrelevant', () => {
    const cards = buildGoalCards(
      profileWith({ learning_context: 'job_interview', learning_context_detail: { label: 'Job Interview' } as any }),
      'AWS CI/CD',
      [{ situation: 'Job Interview', verdict: 'irrelevant' }]
    );
    expect(cards.some((c) => c.key === 'context')).toBe(false);
  });
});
