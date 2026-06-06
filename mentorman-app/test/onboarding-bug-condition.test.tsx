/**
 * Task 1 — Bug Condition Exploration Property Test
 *
 * Property 1: Failed Save Produces No Retry Button
 *
 * Validates: Requirements 1.1, 1.2, 1.3
 *
 * CRITICAL: This test MUST FAIL on unfixed code.
 * Failure here confirms the bug exists — no retry button is rendered
 * after /api/onboarding/complete returns a failure.
 *
 * Bug Condition:
 *   isBugCondition(input) = (input.threwNetworkError = true
 *                            OR input.fetchResponse.ok = false)
 *                           AND profileAlreadyCollected = true
 *                           AND retryOptionShown = false
 *
 * Scoped to two concrete failing cases:
 *   (a) /api/onboarding/complete returns { status: 500, ok: false }
 *   (b) /api/onboarding/complete throws TypeError: Failed to fetch
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import * as fc from 'fast-check';
import { Onboarding } from '../app/components/mentorman/screens';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock @clerk/nextjs so the component can render without a real Clerk context
vi.mock('@clerk/nextjs', () => ({
  useClerk: () => ({ signOut: vi.fn() }),
}));

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

/**
 * Generates a valid CompletedProfile object with random string fields.
 * All four fields are required by the component.
 */
const completedProfileArb = fc.record({
  goal: fc.string({ minLength: 1, maxLength: 120 }),
  deadline: fc.string({ minLength: 1, maxLength: 40 }),
  overall_level: fc.string({ minLength: 1, maxLength: 40 }),
  daily_availability: fc.string({ minLength: 1, maxLength: 40 }),
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type CompletedProfile = {
  goal: string;
  deadline: string;
  overall_level: string;
  daily_availability: string;
};

/**
 * Builds a mock fetch that:
 *  - Returns a successful chat response with complete:true and the given profile
 *    for /api/onboarding/chat
 *  - Returns a 500 non-2xx response for /api/onboarding/complete
 */
function mockFetchWith500(profile: CompletedProfile) {
  return vi.fn(async (url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('/api/onboarding/chat')) {
      return {
        ok: true,
        json: async () => ({
          text: 'Great, I have all the info I need.',
          complete: true,
          profile,
          suggestions: [],
        }),
      } as unknown as Response;
    }
    if (urlStr.includes('/api/onboarding/complete')) {
      // Simulate a 500 non-2xx response
      return {
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal Server Error' }),
      } as unknown as Response;
    }
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
}

/**
 * Builds a mock fetch that:
 *  - Returns a successful chat response with complete:true and the given profile
 *    for /api/onboarding/chat
 *  - Throws TypeError: Failed to fetch for /api/onboarding/complete
 */
function mockFetchWithNetworkError(profile: CompletedProfile) {
  return vi.fn(async (url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('/api/onboarding/chat')) {
      return {
        ok: true,
        json: async () => ({
          text: 'Great, I have all the info I need.',
          complete: true,
          profile,
          suggestions: [],
        }),
      } as unknown as Response;
    }
    if (urlStr.includes('/api/onboarding/complete')) {
      // Simulate a network error (fetch throws)
      throw new TypeError('Failed to fetch');
    }
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('Property 1 — Bug Condition: Failed Save Produces No Retry Button', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Case (a): /api/onboarding/complete returns { status: 500, ok: false }
  // -------------------------------------------------------------------------
  it(
    'PBT: for any CompletedProfile, a 500 response from /api/onboarding/complete should render a retry button (EXPECTED TO FAIL on unfixed code)',
    async () => {
      await fc.assert(
        fc.asyncProperty(completedProfileArb, async (profile) => {
          // Arrange
          vi.stubGlobal('fetch', mockFetchWith500(profile));

          const { unmount } = render(
            <Onboarding onFinish={vi.fn()} userName="Test User" />
          );

          try {
            // Act — wait for the component to finish the chat fetch and attempt the save.
            // We first wait for the chat response to render (mentor message appears),
            // then check whether a retry button is present.
            await waitFor(
              () => {
                // The chat response text rendered means callAgent has run and
                // /api/onboarding/complete has been called and resolved.
                const mentorText = screen.queryByText(/great, i have all the info/i);
                if (!mentorText) {
                  throw new Error('Chat response not yet rendered');
                }
              },
              { timeout: 4000 }
            );

            // Assert: a retry button must be present after the failed save.
            // On UNFIXED code this will FAIL — no retry button is rendered.
            const retryButton = screen.queryByRole('button', { name: /retry/i });
            expect(
              retryButton,
              `BUG CONFIRMED [500 case]: No retry button found after failed save. Profile: ${JSON.stringify(profile)}`
            ).not.toBeNull();

            // Also assert the "Setup complete" card is NOT shown (setDone never called)
            const setupCard = screen.queryByText(/setup complete/i);
            expect(setupCard).not.toBeInTheDocument();
          } finally {
            unmount();
          }
        }),
        {
          // Limit runs to keep the test fast; we only need to confirm one counterexample
          numRuns: 5,
          verbose: true,
        }
      );
    },
    30000 // test-level timeout: 30s to accommodate 5 async PBT runs
  );

  // -------------------------------------------------------------------------
  // Case (b): /api/onboarding/complete throws TypeError: Failed to fetch
  // -------------------------------------------------------------------------
  it(
    'PBT: for any CompletedProfile, a network error from /api/onboarding/complete should render a retry button (EXPECTED TO FAIL on unfixed code)',
    async () => {
      await fc.assert(
        fc.asyncProperty(completedProfileArb, async (profile) => {
          // Arrange
          vi.stubGlobal('fetch', mockFetchWithNetworkError(profile));

          const { unmount } = render(
            <Onboarding onFinish={vi.fn()} userName="Test User" />
          );

          try {
            // Act — wait for the component to finish processing the chat fetch and the save attempt.
            await waitFor(
              () => {
                const mentorText = screen.queryByText(/great, i have all the info/i);
                if (!mentorText) {
                  throw new Error('Chat response not yet rendered');
                }
              },
              { timeout: 4000 }
            );

            // Assert: a retry button must be present after the network error.
            // On UNFIXED code this will FAIL — no retry button is rendered.
            const retryButton = screen.queryByRole('button', { name: /retry/i });
            expect(
              retryButton,
              `BUG CONFIRMED [network-error case]: No retry button found after fetch threw. Profile: ${JSON.stringify(profile)}`
            ).not.toBeNull();

            // Also confirm "Setup complete" card is absent
            const setupCard = screen.queryByText(/setup complete/i);
            expect(setupCard).not.toBeInTheDocument();
          } finally {
            unmount();
          }
        }),
        {
          numRuns: 5,
          verbose: true,
        }
      );
    },
    30000 // test-level timeout: 30s to accommodate 5 async PBT runs
  );
});
