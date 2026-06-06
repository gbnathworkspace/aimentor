# Onboarding Flow Fixes — Bugfix Design

## Overview

After the AI mentor finishes collecting onboarding data, the `Onboarding` component in `screens.tsx` calls `POST /api/onboarding/complete` to persist the profile. Two problems exist:

1. **Client side** — when the fetch fails (network error or non-2xx response), the component appends an error message to the chat thread but offers no retry mechanism. `setDone(true)` is never reached, the "Setup complete" card never renders, and the user is stuck permanently unless they refresh the page and repeat the full conversation.

2. **Server side** — the route handler in `app/api/onboarding/complete/route.ts` has no try/catch around the database call. Any Prisma error or auth failure surfaces as an unhandled exception and returns a plain Next.js 500 with no JSON body, giving the client nothing actionable to display.

The fix targets these two surfaces: add a retry button in the `Onboarding` component that re-attempts the save without losing the collected profile, and wrap the server route in error handling that returns a structured JSON error body with server-side logging.

---

## Glossary

- **Bug_Condition (C)**: The condition that triggers the stuck state — `POST /api/onboarding/complete` returns a non-2xx status or throws a network error after the AI emits a complete profile.
- **Property (P)**: The desired behavior when the bug condition holds — the user is shown an inline retry option and can re-attempt the save without restarting the conversation.
- **Preservation**: All behaviors that must be unchanged by the fix — successful first-try saves, in-progress chat, already-onboarded routing, and ongoing message exchange.
- **`callAgent`**: The async function inside `Onboarding` (in `app/components/mentorman/screens.tsx`) that calls `/api/onboarding/chat`, then conditionally calls `/api/onboarding/complete` when `complete === true`.
- **`setDone`**: React state setter inside `Onboarding` that, when called with `true`, causes the "Setup complete" card to render and hides the composer.
- **`profile`**: The `CompletedProfile` object (`{ goal, deadline, overall_level, daily_availability }`) emitted by the AI and held in React state; it must survive a failed save so a retry can use it.
- **`CoreProfileRepo.upsert`**: The Prisma repository method called by the server route to write the profile to the database.

---

## Bug Details

### Bug Condition

The bug manifests when `complete === true` is returned from `/api/onboarding/chat` AND the subsequent `POST /api/onboarding/complete` either throws (network error) or resolves with a non-2xx status. At that point the component has already set `profile` state with the collected data, but because the save fails, `setDone(true)` is never called and no retry path is offered.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type { fetchResponse: Response | null, threwNetworkError: boolean }
  OUTPUT: boolean

  RETURN (input.threwNetworkError = true
          OR (input.fetchResponse IS NOT NULL
              AND input.fetchResponse.ok = false))
         AND profileAlreadyCollected = true
         AND retryOptionShown = false
END FUNCTION
```

### Examples

- **Non-2xx response**: AI completes data collection; `fetch('/api/onboarding/complete')` returns `{ status: 500 }`. Component shows "I couldn't save your profile…" error bubble. No retry button. User is stuck.
- **Network error**: Device loses connectivity after AI finishes. `fetch` throws `TypeError: Failed to fetch`. The outer `catch` block in `callAgent` appends "Sorry, I lost connection…". No retry button. User is stuck.
- **Auth error (401)**: Clerk session expires mid-onboarding. Server returns 401. Same outcome — error bubble, no retry, stuck.
- **Successful first save** (non-bug): `fetch` returns `{ ok: true }`. `setTimeout(() => setDone(true), 400)` fires. "Setup complete" card renders. User proceeds normally. *(This path must be preserved.)*

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Successful saves (`res.ok === true`) MUST continue to trigger `setDone(true)` after ~400ms and show the "Setup complete" card.
- The conversational chat interface MUST continue to accept user replies while the profile is still being collected (`complete === false`).
- Users who are already onboarded (profile exists in DB) MUST continue to bypass the `Onboarding` component entirely and land directly on the chat screen.
- Ongoing message exchange during the onboarding conversation MUST continue to call `/api/onboarding/chat` and display AI responses correctly.

**Scope:**
All inputs that do NOT involve a failed `/api/onboarding/complete` call should be completely unaffected by this fix. This includes:
- Normal message sends to `/api/onboarding/chat`
- Successful profile saves on first try
- Page loads for already-onboarded users
- The `EvalPanel`, `SessionEnd`, `Settings`, and `MobileChat` components

---

## Hypothesized Root Cause

Based on reading `screens.tsx` and the server route:

1. **No retry state in `Onboarding` component**: After a failed save, `profile` is already in state but there is no `saveFailed` flag and no UI element to re-trigger the save. The error path simply `return`s out of `callAgent`, discarding the retry opportunity.

2. **`.catch(() => null)` swallows all error detail**: The fetch call uses `.catch(() => null)`, which collapses network errors and non-2xx responses into the same `!res?.ok` check. There is no distinction between a transient network failure (retry makes sense) and a permanent error (different message may be warranted), though for MVP a single retry path is sufficient.

3. **Server route has no try/catch**: `CoreProfileRepo.upsert(...)` is awaited without error handling. Any Prisma or auth exception propagates as an unhandled rejection, causing Next.js to return a generic HTML 500 page instead of a JSON body. The client receives an unparseable response.

4. **`requireUserId()` can throw before any response is sent**: If the Clerk helper throws (e.g., expired session), there is no catch and no meaningful HTTP response body.

---

## Correctness Properties

Property 1: Bug Condition — Failed Save Surfaces Inline Retry

_For any_ state where the AI has returned `complete: true` (a `CompletedProfile` has been collected) AND the `POST /api/onboarding/complete` call fails (network error or non-2xx response), the fixed `Onboarding` component SHALL display an inline retry button in the chat thread so the user can re-attempt the save without restarting the conversation, and SHALL NOT enter a permanently stuck state.

**Validates: Requirements 2.1, 1.1, 1.2, 1.3**

Property 2: Preservation — Successful Save Path Is Unchanged

_For any_ state where the `POST /api/onboarding/complete` call succeeds (`res.ok === true`) on the first attempt, the fixed component SHALL produce the same result as the original component — calling `setDone(true)` after ~400ms and rendering the "Setup complete" card — preserving the happy-path user experience.

**Validates: Requirements 3.2, 2.2**

---

## Fix Implementation

### Changes Required

**File 1:** `app/components/mentorman/screens.tsx`

**Component:** `Onboarding`

**Specific Changes:**

1. **Add `saveFailed` state**: Introduce `const [saveFailed, setSaveFailed] = useState(false)` to track whether the most recent save attempt failed.

2. **Add `attemptSave` function**: Extract the `/api/onboarding/complete` fetch into a standalone `attemptSave(p: CompletedProfile)` function so it can be called both from `callAgent` (first attempt) and from a retry button (subsequent attempts).

   ```ts
   const attemptSave = async (p: CompletedProfile) => {
     setSaveFailed(false);
     const res = await fetch('/api/onboarding/complete', {
       method:  'POST',
       headers: { 'Content-Type': 'application/json' },
       body:    JSON.stringify(p),
     }).catch(() => null);
     if (!res?.ok) {
       setSaveFailed(true);
       return;
     }
     setSaveFailed(false);
     setTimeout(() => setDone(true), 400);
   };
   ```

3. **Update `callAgent`**: Replace the inline fetch block with a call to `attemptSave(p)` after `setProfile(p)`.

4. **Render retry UI when `saveFailed === true`**: In the JSX, below the thread messages and above the `{done && ...}` card, render a retry element when `saveFailed` is true:

   ```tsx
   {saveFailed && profile && !done && (
     <div className="onb-save-error">
       <span>Couldn&apos;t save your profile — please check your connection.</span>
       <button
         className="btn btn-sm btn-accent"
         disabled={busy}
         onClick={() => attemptSave(profile)}
       >
         Retry
       </button>
     </div>
   )}
   ```

5. **Remove the old error-message push for save failures**: Delete the `setThread(prev => [...prev, { who: 'mentor', text: "I couldn't save your profile…", … }])` block from `callAgent`, replacing it with the `setSaveFailed(true)` path above. This prevents duplicate error messages on re-render.

---

**File 2:** `app/api/onboarding/complete/route.ts`

**Function:** `POST`

**Specific Changes:**

1. **Wrap handler body in try/catch**: Catch any error from `requireUserId()` or `CoreProfileRepo.upsert(...)`.

2. **Return structured JSON error on failure**: Return `NextResponse.json({ ok: false, error: 'Failed to save profile' }, { status: 500 })` so the client always receives parseable JSON.

3. **Log server-side**: Call `console.error('onboarding/complete error:', err)` inside the catch block so failures are visible in server logs.

   ```ts
   export async function POST(req: NextRequest) {
     try {
       const uid = await requireUserId();
       const { goal, deadline, overall_level, daily_availability } = await req.json();

       await CoreProfileRepo.upsert({
         userId: uid,
         goal,
         deadline,
         overall_level: overall_level ?? 'beginner',
         daily_availability: daily_availability ?? '2 hrs/day',
         email: '',
       });

       return NextResponse.json({ ok: true });
     } catch (err) {
       console.error('onboarding/complete error:', err);
       return NextResponse.json(
         { ok: false, error: 'Failed to save profile' },
         { status: 500 }
       );
     }
   }
   ```

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the stuck state on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If refuted, re-hypothesize.

**Test Plan**: Render the `Onboarding` component in a test environment with `fetch` mocked to return a failed response for `/api/onboarding/complete`. Simulate the AI returning `complete: true` with a valid profile. Assert that a retry button appears — this will fail on unfixed code because no retry UI exists.

**Test Cases:**
1. **Non-2xx save failure**: Mock `/api/onboarding/complete` to return `{ status: 500, ok: false }`. After chat completes, assert a retry button is present in the DOM. *(Fails on unfixed code — no retry button rendered.)*
2. **Network error save failure**: Mock `fetch` to throw `new TypeError('Failed to fetch')` for `/api/onboarding/complete`. After chat completes, assert a retry button is present. *(Fails on unfixed code.)*
3. **Stuck state permanence**: After the failed save on unfixed code, assert that `setDone` was never called and the "Setup complete" card is absent. *(Passes — confirms the stuck state.)*
4. **Server route unhandled error**: Call the server route handler directly with a mock that makes `CoreProfileRepo.upsert` throw. Assert the response is a valid JSON object with `ok: false`. *(Fails on unfixed code — unhandled exception returns no JSON body.)*

**Expected Counterexamples:**
- Retry button is absent after a failed save — confirms Requirement 1.3 defect.
- Server route returns non-JSON on DB error — confirms Requirement 2.3 defect.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed code produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  render Onboarding component
  simulate AI completing profile collection
  mock fetch('/api/onboarding/complete') to fail
  result := inspect rendered DOM
  ASSERT retryButtonPresent(result) = true
  ASSERT setupCompleteCardPresent(result) = false
  click retry button
  mock fetch('/api/onboarding/complete') to succeed
  ASSERT setupCompleteCardPresent(result) = true
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed component produces the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT fixedComponent(input) = originalComponent(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (varied message sequences, different profile shapes).
- It catches edge cases that manual unit tests might miss (e.g., partial profiles, unusual availability strings).
- It provides strong guarantees that successful-save behavior is unchanged for all non-buggy inputs.

**Test Plan**: Observe behavior on UNFIXED code first for successful saves, in-progress chat, and already-onboarded routing, then write property-based tests capturing that behavior.

**Test Cases:**
1. **Successful save preservation**: Mock `/api/onboarding/complete` to return `{ ok: true }`. Assert `setDone(true)` is called after ~400ms and the "Setup complete" card renders — same as original behavior.
2. **In-progress chat preservation**: While `complete === false`, assert the composer remains visible and sending a message calls `/api/onboarding/chat`.
3. **Already-onboarded bypass preservation**: This is tested at the `app.tsx` / routing level, not inside `Onboarding` itself — verify the component is not rendered when a profile already exists.
4. **Other keyboard / interaction preservation**: Verify the retry button does not interfere with the chat composer when `saveFailed === false`.

### Unit Tests

- Test `attemptSave` in isolation: mock `fetch` to succeed, fail with non-2xx, and throw — verify `setSaveFailed` and `setDone` state transitions for each case.
- Test the server route handler with mocked `CoreProfileRepo.upsert` throwing — verify the response is `{ ok: false, error: '...' }` with status 500.
- Test the server route handler with a successful upsert — verify the response is `{ ok: true }` with status 200.
- Test that the retry button click calls `attemptSave` with the stored `profile` object.

### Property-Based Tests

- Generate random `CompletedProfile` objects (varied goal strings, deadline formats, level values, availability text) and assert that a successful save always transitions to `done === true` within 1 second.
- Generate random sequences of `(fail N times, then succeed)` and assert the user can always eventually reach the "Setup complete" card via repeated retries.
- Generate random non-complete chat messages and assert the retry UI never appears when `saveFailed === false`.

### Integration Tests

- Full onboarding flow: simulate the full conversation until AI emits `onboarding_complete`, mock the first save to fail, click retry, mock the second save to succeed — assert the "Setup complete" card renders and "Start your first session" button is clickable.
- Verify that after a failed save followed by a successful retry, clicking "Start your first session" correctly calls `onFinish(profile.goal)`.
- Verify the server route returns a parseable JSON body under simulated DB failure, and that the client-side retry logic correctly reads `res.ok` rather than attempting to parse the body.
