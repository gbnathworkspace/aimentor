import { describe, it, expect } from 'vitest';
import {
  determinePhasesToSkip,
  PLACEHOLDER_GOAL,
  PLACEHOLDER_AVAILABILITY,
} from '@/app/components/mentorman/useDeferredOnboarding';

describe('determinePhasesToSkip', () => {
  describe('Phase 0 (Goal & Timeline)', () => {
    it('skips phase 0 when goal is non-placeholder AND deadline is non-null', () => {
      const result = determinePhasesToSkip({
        goal: 'crack FAANG interviews',
        deadline: '2025-09-01',
        overall_level: 'beginner',
        daily_availability: '1 hour',
      });
      expect(result).toContain(0);
    });

    it('does NOT skip phase 0 when goal is the placeholder "exploring"', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: '2025-09-01',
        overall_level: 'beginner',
        daily_availability: '1 hour',
      });
      expect(result).not.toContain(0);
    });

    it('does NOT skip phase 0 when deadline is null', () => {
      const result = determinePhasesToSkip({
        goal: 'get a dev job',
        deadline: null,
        overall_level: 'beginner',
        daily_availability: '1 hour',
      });
      expect(result).not.toContain(0);
    });

    it('does NOT skip phase 0 when both goal is placeholder and deadline is null', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: null,
        overall_level: 'beginner',
        daily_availability: '1 hour',
      });
      expect(result).not.toContain(0);
    });
  });

  describe('Phase 1 (Current State)', () => {
    it('skips phase 1 when overall_level is not "beginner"', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: null,
        overall_level: 'intermediate',
        daily_availability: '1 hour',
      });
      expect(result).toContain(1);
    });

    it('does NOT skip phase 1 when overall_level is "beginner"', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: null,
        overall_level: 'beginner',
        daily_availability: '1 hour',
      });
      expect(result).not.toContain(1);
    });
  });

  describe('Phase 2 (File Upload)', () => {
    it('never skips phase 2 — always included in deferred mode', () => {
      const result = determinePhasesToSkip({
        goal: 'crack FAANG',
        deadline: '2025-12-01',
        overall_level: 'advanced',
        daily_availability: '4 hrs/day',
      });
      expect(result).not.toContain(2);
    });
  });

  describe('Phase 3 (Availability)', () => {
    it('skips phase 3 when daily_availability is not "1 hour"', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: null,
        overall_level: 'beginner',
        daily_availability: '3 hrs/day',
      });
      expect(result).toContain(3);
    });

    it('does NOT skip phase 3 when daily_availability is "1 hour"', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: null,
        overall_level: 'beginner',
        daily_availability: PLACEHOLDER_AVAILABILITY,
      });
      expect(result).not.toContain(3);
    });
  });

  describe('combined scenarios', () => {
    it('skips nothing for a fully-default profile', () => {
      const result = determinePhasesToSkip({
        goal: PLACEHOLDER_GOAL,
        deadline: null,
        overall_level: 'beginner',
        daily_availability: PLACEHOLDER_AVAILABILITY,
      });
      expect(result).toEqual([]);
    });

    it('skips all non-file phases when all fields are user-provided', () => {
      const result = determinePhasesToSkip({
        goal: 'land SWE job at Google',
        deadline: '2025-06-15',
        overall_level: 'intermediate',
        daily_availability: '2 hrs weekdays',
      });
      // Should skip phases 0, 1, 3 (phase 2 is never skipped)
      expect(result).toContain(0);
      expect(result).toContain(1);
      expect(result).not.toContain(2);
      expect(result).toContain(3);
    });

    it('returns the start phase as the first non-skipped phase', () => {
      // Phases 0, 1 skipped → start at phase 2
      const result = determinePhasesToSkip({
        goal: 'become ML engineer',
        deadline: '2026-01-01',
        overall_level: 'advanced',
        daily_availability: '1 hour', // placeholder → phase 3 NOT skipped
      });
      expect(result).toContain(0);
      expect(result).toContain(1);
      expect(result).not.toContain(2);
      expect(result).not.toContain(3);
    });

    it('handles empty/undefined fields as incomplete', () => {
      const result = determinePhasesToSkip({
        goal: undefined as unknown as string,
        deadline: undefined as unknown as string,
        overall_level: undefined as unknown as string,
        daily_availability: undefined as unknown as string,
      });
      expect(result).toEqual([]);
    });
  });
});
