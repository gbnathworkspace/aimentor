'use client';

import { useState, useEffect } from 'react';

// ─── Placeholder / default values (matches skip-onboarding spec) ──────────────
const PLACEHOLDER_GOAL = 'exploring';
const PLACEHOLDER_AVAILABILITY = '1 hour';

/**
 * Phase mapping:
 *   Phase 0: Goal & Timeline → goal, deadline
 *   Phase 1: Current State → overall_level
 *   Phase 2: File Upload → always included in deferred mode
 *   Phase 3: Availability → daily_availability
 */
export interface DeferredOnboardingState {
  /** Whether the profile has been loaded from the server */
  loaded: boolean;
  /** Whether this is a deferred onboarding session */
  isDeferred: boolean;
  /** Phases that should be skipped (0-indexed) */
  phasesToSkip: number[];
  /** The first phase to start from (0-3) */
  startPhase: number;
  /** Existing profile data from the server */
  existingProfile: {
    goal?: string;
    deadline?: string | null;
    overall_level?: string;
    daily_availability?: string;
  } | null;
  /** Error during profile fetch */
  error: string | null;
}

/**
 * Determines which onboarding phases to skip based on existing profile data.
 *
 * Rules (from spec):
 * - Phase 0 (Goal & Timeline): skip if goal ≠ "exploring" AND deadline ≠ null
 * - Phase 1 (Current State): skip if overall_level ≠ "beginner"
 * - Phase 2 (File Upload): always include in deferred mode
 * - Phase 3 (Availability): skip if daily_availability ≠ "1 hour"
 */
function determinePhasesToSkip(profile: {
  goal?: string;
  deadline?: string | null;
  overall_level?: string;
  daily_availability?: string;
}): number[] {
  const skip: number[] = [];

  // Phase 0: skip if goal is non-placeholder AND deadline is non-null
  const goalCompleted = profile.goal && profile.goal !== PLACEHOLDER_GOAL;
  const deadlineCompleted = profile.deadline !== null && profile.deadline !== undefined && profile.deadline !== '';
  if (goalCompleted && deadlineCompleted) {
    skip.push(0);
  }

  // Phase 1: skip if overall_level is not "beginner" (default/placeholder)
  if (profile.overall_level && profile.overall_level !== 'beginner') {
    skip.push(1);
  }

  // Phase 2: File Upload — always included in deferred mode (never skip)

  // Phase 3: skip if daily_availability is non-placeholder
  if (profile.daily_availability && profile.daily_availability !== PLACEHOLDER_AVAILABILITY) {
    skip.push(3);
  }

  return skip;
}

/**
 * Hook that manages deferred onboarding state.
 * Fetches the existing profile and determines which phases to skip.
 *
 * @param enabled - Whether deferred mode is active
 */
export function useDeferredOnboarding(enabled: boolean): DeferredOnboardingState {
  const [state, setState] = useState<DeferredOnboardingState>({
    loaded: false,
    isDeferred: enabled,
    phasesToSkip: [],
    startPhase: 0,
    existingProfile: null,
    error: null,
  });

  useEffect(() => {
    if (!enabled) {
      setState({
        loaded: true,
        isDeferred: false,
        phasesToSkip: [],
        startPhase: 0,
        existingProfile: null,
        error: null,
      });
      return;
    }

    let cancelled = false;

    async function fetchProfile() {
      try {
        const res = await fetch('/api/profile');
        if (!res.ok) {
          if (!cancelled) {
            setState(prev => ({
              ...prev,
              loaded: true,
              error: 'Could not load your profile. Starting from the beginning.',
            }));
          }
          return;
        }

        const profile = await res.json();
        if (cancelled) return;

        const phasesToSkip = determinePhasesToSkip(profile);

        // Find the first phase NOT in phasesToSkip
        let startPhase = 0;
        for (let i = 0; i <= 3; i++) {
          if (!phasesToSkip.includes(i)) {
            startPhase = i;
            break;
          }
        }

        setState({
          loaded: true,
          isDeferred: true,
          phasesToSkip,
          startPhase,
          existingProfile: {
            goal: profile.goal,
            deadline: profile.deadline,
            overall_level: profile.overall_level,
            daily_availability: profile.daily_availability,
          },
          error: null,
        });
      } catch {
        if (!cancelled) {
          setState(prev => ({
            ...prev,
            loaded: true,
            error: 'Could not load your profile. Starting from the beginning.',
          }));
        }
      }
    }

    fetchProfile();
    return () => { cancelled = true; };
  }, [enabled]);

  return state;
}

// Export for testing
export { determinePhasesToSkip, PLACEHOLDER_GOAL, PLACEHOLDER_AVAILABILITY };
