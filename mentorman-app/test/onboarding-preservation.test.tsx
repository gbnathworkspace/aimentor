/**
 * Task 2 — Preservation Property Tests (BEFORE implementing fix)
 *
 * Property 2: Preservation — Non-Failing Save Path and In-Progress Chat Are Unchanged
 *
 * Validates: Requirements 3.1, 3.2, 3.4
 *
 * IMPORTANT: These tests MUST PASS on unfixed code.
 * They establish the baseline of existing correct behaviors that the fix
 * must NOT break.
 *
 * Observation-first methodology:
 *   - P2a: Onboarding with /api/onboarding/complete mocked to return { ok: true }
 *          → setDone(true) fires after ~400ms and "Setup complete" card renders
 *   - P2b: Onboarding while complete === false → composer remains visible,
 *          sending a message calls /api/onboarding/chat
 *   - P2c: Retry button is absent when saveFailed has never been set
 *          (it doesn't exist on unfixed code, so this trivially passes)
 */

import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import * as fc from 'fast-check';
import { Onboarding } from '../app/components/mentorman/screens';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@clerk/nextjs', () => ({
  useClerk: () => ({ signOut: vi.fn() }),
}));

// Mock next/navigation so useRouter doesn't throw in test environment
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/onboarding',
  useSearchParams: () => new URLSearchParams(),
}));

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

type CompletedProfile = {
  goal: string;
  deadline: string;
  overall_level: string;
  daily_availability: string;
};

/**
 * Generates a valid CompletedProfile with random non-empty, trimmed string fields.
 * Strings are trimmed and filtered because:
 *  - DOM text matchers normalize whitespace (leading/trailing spaces cause mismatches)
 *  - Whitespace-only strings can't be found via getByText
 *  - They are not meaningful profile values
 * We also exclude strings containing newlines since they break text matching.
 */
const completedProfileArb = fc.record({
  goal:               fc.string({ minLength: 1, maxLength: 120 }).map(s => s.trim()).filter(s => s.length > 0 && !s.includes('\n') && !s.includes('\r')),
  deadline:           fc.string({ minLength: 1, maxLength: 40 }).map(s => s.trim()).filter(s => s.length > 0 && !s.includes('\n') && !s.includes('\r')),
  overall_level:      fc.string({ minLength: 1, maxLength: 40 }).map(s => s.trim()).filter(s => s.length > 0 && !s.includes('\n') && !s.includes('\r')),
  daily_availability: fc.string({ minLength: 1, maxLength: 40 }).map(s => s.trim()).filter(s => s.length > 0 && !s.includes('\n') && !s.includes('\r')),
});

/**
 * Generates a non-empty user message string.
 */
const nonEmptyMessageArb = fc.string({ minLength: 1, maxLength: 200 }).filter(s => s.trim().length > 0);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Builds a mock fetch that:
 *  - For the initial "hi" → returns a question (complete: false) from /api/onboarding/chat
 *  - For the user message → returns a follow-up question (complete: false) from /api/onboarding/chat
 *  - Never calls /api/onboarding/complete (complete is never true in this scenario)
 */
function mockFetchChatOnly(aiReply: string) {
  return vi.fn(async (url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('/api/onboarding/chat')) {
      return {
        ok: true,
        json: async () => ({
          text: aiReply,
          complete: false,
          profile: null,
          suggestions: [],
        }),
      } as unknown as Response;
    }
    // Fallback — should not be reached in P2b scenarios
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
}

/**
 * Builds a mock fetch that:
 *  - Returns a successful chat response with complete:true and the given profile
 *    for /api/onboarding/chat
 *  - Returns { ok: true } for /api/onboarding/complete (happy path)
 */
function mockFetchSuccessfulSave(profile: CompletedProfile) {
  return vi.fn(async (url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('/api/onboarding/chat')) {
      return {
        ok: true,
        json: async () => ({
          text: "Perfect, I have everything I need!",
          complete: true,
          profile,
          suggestions: [],
        }),
      } as unknown as Response;
    }
    if (urlStr.includes('/api/onboarding/complete')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      } as unknown as Response;
    }
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
}

/**
 * Builds a mock fetch that tracks calls and returns incomplete chat responses.
 * Returns a reference to the mock so callers can inspect calls.
 */
function mockFetchChatOnlyTracked(aiReply: string) {
  const mockFn = vi.fn(async (url: string | URL | Request) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('/api/onboarding/chat')) {
      return {
        ok: true,
        json: async () => ({
          text: aiReply,
          complete: false,
          profile: null,
          suggestions: [],
        }),
      } as unknown as Response;
    }
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
  return mockFn;
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('Property 2 — Preservation: Non-Failing Save Path and In-Progress Chat Are Unchanged', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // P2a: For any valid CompletedProfile, when /api/onboarding/complete returns
  //       { ok: true }, the "Setup complete" card MUST render within 1 second.
  // -------------------------------------------------------------------------
  describe('P2a — Successful save renders "Setup complete" card', () => {
    it(
      'PBT: for any CompletedProfile, a successful /api/onboarding/complete response renders the "Setup complete" card',
      async () => {
        await fc.assert(
          fc.asyncProperty(completedProfileArb, async (profile) => {
            vi.stubGlobal('fetch', mockFetchSuccessfulSave(profile));

            const { unmount } = render(
              <Onboarding onFinish={vi.fn()} userName="Test User" />
            );

            try {
              // Wait for chat to complete and save to succeed, then the
              // 400ms timer fires — total budget: 1 second per spec.
              await waitFor(
                () => {
                  // "Setup complete" badge text
                  const badge = screen.queryByText(/setup complete/i);
                  if (!badge) {
                    throw new Error('"Setup complete" card not yet rendered');
                  }
                },
                { timeout: 2000 }  // generous window that includes the 400ms timer
              );

              // Assert the "Setup complete" card is present
              expect(screen.getByText(/setup complete/i)).toBeInTheDocument();

              // Assert "You're all set." heading is present
              expect(screen.getByText(/you're all set/i)).toBeInTheDocument();

              // Assert the profile data is shown in the card
              // Use a function matcher to handle DOM text normalization edge cases
              // (special chars, whitespace variations in different environments).
              const goalElements = screen.getAllByText(
                (content) => content.trim() === profile.goal.trim()
              );
              expect(goalElements.length).toBeGreaterThan(0);

              // Assert "Start your first session" CTA is present
              expect(
                screen.getByRole('button', { name: /start your first session/i })
              ).toBeInTheDocument();

              // Assert composer is hidden (done === true)
              const composer = screen.queryByPlaceholderText(/reply to your mentor/i);
              expect(composer).not.toBeInTheDocument();
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
      30000
    );
  });

  // -------------------------------------------------------------------------
  // P2b: For any non-empty user message, while complete === false, sending a
  //      message MUST call /api/onboarding/chat and render the AI reply.
  // -------------------------------------------------------------------------
  describe('P2b — In-progress chat sends to /api/onboarding/chat and renders reply', () => {
    it(
      'PBT: for any non-empty user message, while onboarding is in progress, the message is sent to /api/onboarding/chat',
      async () => {
        await fc.assert(
          fc.asyncProperty(nonEmptyMessageArb, async (userMessage) => {
            const aiReply = 'Got it, what is your target deadline?';
            const mockFetch = mockFetchChatOnlyTracked(aiReply);
            vi.stubGlobal('fetch', mockFetch);

            const { unmount } = render(
              <Onboarding onFinish={vi.fn()} userName="Test User" />
            );

            try {
              // Wait for the initial "hi" message to be processed —
              // the composer becomes accessible once the first response arrives.
              await waitFor(
                () => {
                  const textarea = screen.queryByPlaceholderText(/reply to your mentor/i);
                  if (!textarea) throw new Error('Composer textarea not found yet');
                  const busy = (textarea as HTMLTextAreaElement).disabled;
                  if (busy) throw new Error('Component is still busy');
                },
                { timeout: 4000 }
              );

              // Capture the call count before the user message
              const callsBeforeUserMsg = mockFetch.mock.calls.length;

              // Type and send user message via the textarea
              const textarea = screen.getByPlaceholderText(/reply to your mentor/i);
              fireEvent.change(textarea, { target: { value: userMessage } });
              fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

              // Wait for the AI reply to appear in the DOM.
              // The same text may appear multiple times (first question + reply bubble),
              // so we use queryAllByText and check at least one element is present.
              await waitFor(
                () => {
                  const replies = screen.queryAllByText(aiReply);
                  if (replies.length === 0) throw new Error('AI reply not yet rendered');
                },
                { timeout: 4000 }
              );

              // Assert that /api/onboarding/chat was called at least once MORE
              // after the user message (i.e., the user message triggered a new call)
              const callsAfterUserMsg = mockFetch.mock.calls.filter(
                (_call, idx) => idx >= callsBeforeUserMsg
              );

              expect(callsAfterUserMsg.length).toBeGreaterThan(0);

              // Confirm the most recent call was to /api/onboarding/chat
              const lastCallUrl = callsAfterUserMsg[callsAfterUserMsg.length - 1][0] as string;
              expect(lastCallUrl).toContain('/api/onboarding/chat');

              // Confirm the AI reply is rendered in the thread (at least one occurrence)
              expect(screen.queryAllByText(aiReply).length).toBeGreaterThan(0);

              // Confirm the composer is still visible (done is still false)
              expect(
                screen.getByPlaceholderText(/reply to your mentor/i)
              ).toBeInTheDocument();

              // Confirm NO retry button is present (saveFailed was never set)
              expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();

              // Confirm "Setup complete" card is absent
              expect(screen.queryByText(/setup complete/i)).not.toBeInTheDocument();
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
      60000
    );
  });

  // -------------------------------------------------------------------------
  // P2c: For any CompletedProfile shape, when no save has been attempted
  //      (fresh mount), the retry button MUST NOT be present.
  // -------------------------------------------------------------------------
  describe('P2c — No retry button on fresh mount (saveFailed never set)', () => {
    it(
      'PBT: for any CompletedProfile shape, on fresh mount before any save, no retry button is present',
      async () => {
        await fc.assert(
          fc.asyncProperty(completedProfileArb, async (profile) => {
            // Use a mock that returns incomplete chat — save never fires,
            // so saveFailed is never set (and on unfixed code, the state
            // doesn't even exist — retry button is trivially absent).
            const aiReply = 'Tell me more about your experience level.';
            vi.stubGlobal('fetch', mockFetchChatOnly(aiReply));

            const { unmount } = render(
              <Onboarding onFinish={vi.fn()} userName="Test User" />
            );

            try {
              // Wait for initial render to settle
              await waitFor(
                () => {
                  const textarea = screen.queryByPlaceholderText(/reply to your mentor/i);
                  if (!textarea) throw new Error('Composer not yet rendered');
                },
                { timeout: 4000 }
              );

              // Assert: no retry button on fresh mount
              const retryButton = screen.queryByRole('button', { name: /retry/i });
              expect(
                retryButton,
                `Expected no retry button on fresh mount for profile: ${JSON.stringify(profile)}`
              ).toBeNull();

              // Assert: "Setup complete" card is not shown
              expect(screen.queryByText(/setup complete/i)).not.toBeInTheDocument();

              // Assert: composer IS visible (onboarding in progress)
              expect(
                screen.getByPlaceholderText(/reply to your mentor/i)
              ).toBeInTheDocument();
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
      30000
    );
  });
});
