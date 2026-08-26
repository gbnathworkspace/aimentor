# Implementation Plan

## Overview

This plan follows the exploratory bugfix workflow for the onboarding stuck-state bug. Tests are written before the fix to understand and document the defect, then the fix is applied and validated.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Failed Save Produces No Retry Button
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the stuck state on unfixed code
  - **Scoped PBT Approach**: Scope the property to two concrete failing cases — (a) `/api/onboarding/complete` returns `{ status: 500, ok: false }` and (b) `/api/onboarding/complete` throws `TypeError: Failed to fetch` — with any valid `CompletedProfile` shape
  - Set up test framework: install `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@vitejs/plugin-react`, `fast-check`, and `jsdom` as dev dependencies; add a `vitest.config.ts` and a `test/setup.ts` with `@testing-library/jest-dom` matchers
  - Write a property-based test that generates random `CompletedProfile` objects (`{ goal: string, deadline: string, overall_level: string, daily_availability: string }`) and for each, renders `<Onboarding>` in a test environment, mocks `fetch` so that `/api/onboarding/chat` returns `{ text: "...", complete: true, profile: generatedProfile }` and `/api/onboarding/complete` returns a failing response (non-2xx or throws), then asserts that a retry button is present in the DOM
  - Bug Condition (from design): `isBugCondition(input)` where `input.threwNetworkError = true OR (input.fetchResponse.ok = false)` AND `profileAlreadyCollected = true` AND `retryOptionShown = false`
  - Expected behavior (from design): retry button rendered; "Setup complete" card absent; `setDone` never called
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS — no retry button is rendered by the current `Onboarding` component (confirms bug from Requirements 1.1, 1.2, 1.3)
  - Document counterexamples found (e.g., `CompletedProfile { goal: "Learn React", deadline: "2025-12-31", overall_level: "beginner", daily_availability: "2 hrs/day" }` — retry button absent after 500 response)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Failing Save Path and In-Progress Chat Are Unchanged
  - **IMPORTANT**: Follow observation-first methodology — observe unfixed code behavior before writing assertions
  - Observe on UNFIXED code:
    - `Onboarding` with `/api/onboarding/complete` mocked to return `{ ok: true }` → `setDone(true)` fires after ~400ms and "Setup complete" card renders
    - `Onboarding` while `complete === false` → composer remains visible, sending a message calls `/api/onboarding/chat`
    - Retry button is absent when `saveFailed` has never been set (it doesn't exist on unfixed code, so this trivially passes)
  - Write property-based tests using `fast-check`:
    - **Preservation P2a**: For any valid `CompletedProfile`, when `/api/onboarding/complete` returns `{ ok: true }`, the "Setup complete" card MUST render within 1 second — same as original behavior (from Preservation Requirements in design: "Successful saves MUST continue to trigger `setDone(true)` after ~400ms")
    - **Preservation P2b**: For any non-empty user message string, while `complete === false`, sending a message MUST call `/api/onboarding/chat` and render the AI reply — same as original behavior (from Preservation Requirements: "conversational chat interface MUST continue to accept user replies")
    - **Preservation P2c**: For any `CompletedProfile` shape, when no save has been attempted (fresh mount), the retry button MUST NOT be present — same as original behavior
  - Run all preservation tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 3. Fix for onboarding stuck state — no retry after failed profile save

  - [x] 3.1 Add `saveFailed` state and extract `attemptSave` function in `Onboarding` component
    - In `app/components/mentorman/screens.tsx`, inside the `Onboarding` component, add `const [saveFailed, setSaveFailed] = useState(false)`
    - Extract the `/api/onboarding/complete` fetch into a new `attemptSave(p: CompletedProfile)` async function:
      - Call `setSaveFailed(false)` at the start
      - Fetch `/api/onboarding/complete` with `method: 'POST'`, passing `p` as JSON body; use `.catch(() => null)` to handle network errors
      - If `!res?.ok`, call `setSaveFailed(true)` and return (do NOT push an error bubble to thread)
      - If `res.ok`, call `setSaveFailed(false)` then `setTimeout(() => setDone(true), 400)`
    - _Bug_Condition: `isBugCondition(input)` where `input.fetchResponse.ok = false OR input.threwNetworkError = true` AND `profileAlreadyCollected = true`_
    - _Expected_Behavior: `retryOptionShown = true`; `setDone` not called until a subsequent save succeeds_
    - _Preservation: Successful saves MUST still call `setDone(true)` after ~400ms; chat composer MUST remain active while profile is being collected_
    - _Requirements: 2.1, 2.2, 1.1, 1.2, 1.3_

  - [x] 3.2 Update `callAgent` and render retry UI in `Onboarding`
    - In `callAgent`, replace the inline fetch block (the `const res = await fetch('/api/onboarding/complete', …).catch(…)` block and the `if (!res?.ok)` branch that pushes an error thread message) with a call to `attemptSave(p)` after `setProfile(p)`
    - In the JSX, add the retry UI below the thread messages and above the `{done && profile && (…)}` "Setup complete" card:
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
    - Ensure the old `setThread(prev => [...prev, { who: 'mentor', text: "I couldn't save your profile…", _id: 'err-save'… }])` block is removed from `callAgent`
    - _Requirements: 2.1, 1.3_

  - [x] 3.3 Wrap server route in try/catch and return structured JSON error
    - In `app/api/onboarding/complete/route.ts`, wrap the entire handler body in a `try/catch`
    - In the `catch` block: call `console.error('onboarding/complete error:', err)` and return `NextResponse.json({ ok: false, error: 'Failed to save profile' }, { status: 500 })`
    - The happy path remains `return NextResponse.json({ ok: true })`
    - _Requirements: 2.3_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Failed Save Produces No Retry Button
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 asserts that a retry button is present after a failed save; that assertion now validates the fix
    - Run the Property 1 test suite
    - **EXPECTED OUTCOME**: Test PASSES (confirms the retry button is rendered after a failed `/api/onboarding/complete` call)
    - _Requirements: 2.1, 1.1, 1.2, 1.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Failing Save Path and In-Progress Chat Are Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run the Property 2 test suite (P2a, P2b, P2c)
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — successful saves still show "Setup complete" card, chat composer still works, retry button absent when no failure has occurred)
    - Confirm all tests still pass after fix

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite (`npx vitest run` or equivalent)
  - Confirm Property 1 (Bug Condition) test passes — retry button is rendered on failed save
  - Confirm Property 2 (Preservation) tests pass — successful save, in-progress chat, and no spurious retry button
  - Confirm server route unit tests pass — `{ ok: false, error: '...' }` with status 500 on DB error; `{ ok: true }` on success
  - If any test fails, investigate before proceeding; ask the user if questions arise

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"] },
    { "wave": 2, "tasks": ["3.1"] },
    { "wave": 3, "tasks": ["3.2", "3.3"] },
    { "wave": 4, "tasks": ["3.4", "3.5"] },
    { "wave": 5, "tasks": ["4"] }
  ]
}
```

## Notes

- No test framework is currently installed in `mentorman-app`. Task 1 includes setting up `vitest`, `@testing-library/react`, `@testing-library/user-event`, `fast-check`, and `jsdom` as dev dependencies before writing any tests.
- The `package.json` has no `"prisma"` dependency — the app uses `mongoose`/MongoDB, so `CoreProfileRepo` is the Mongoose abstraction. Mock it accordingly in server-route unit tests.
- The `@clerk/nextjs` auth helper `requireUserId()` must also be mocked in server-route tests since it will throw outside a Clerk context.
- Property 1 is expected to **fail** on unfixed code — this is the correct outcome and confirms the bug exists. Do not skip or suppress the failure.
- Property 2 is expected to **pass** on unfixed code — this establishes the preservation baseline before any changes are made.
