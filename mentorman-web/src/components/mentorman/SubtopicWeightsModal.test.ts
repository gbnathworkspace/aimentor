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
});
