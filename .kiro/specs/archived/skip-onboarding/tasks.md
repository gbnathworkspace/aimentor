# Implementation Plan: Skip Onboarding

## Overview

This plan implements the skip-onboarding feature across the MentorMan web frontend (TypeScript/React) and backend (TypeScript/Next.js API routes). Tasks build from data model changes through backend API logic, context assembler degradation, frontend UI components, and finally wiring everything together with deferred onboarding and banner flows.

## Tasks

- [x] 1. Update CoreProfile schema and data models
  - [x] 1.1 Add `profile_status` field and make `deadline` nullable in CoreProfile schema
    - Update the Zod `CoreProfileSchema` to add `profile_status: z.enum(['complete', 'skipped']).default('complete')`
    - Change `deadline` field to `z.string().nullable()` 
    - Update the Mongoose schema to include `profile_status` with enum constraint and `deadline` with `default: null`
    - Ensure existing profiles default to `profile_status: 'complete'` (backward compatible)
    - _Requirements: 3.1, 3.4, 7.1_

  - [ ]* 1.2 Write property test for CoreProfile schema validation (Property 7)
    - **Property 7: Partial responses override defaults**
    - Generate all 2^3 subsets of {goal, deadline, availability} × random string values
    - Verify that user-provided fields appear in the resulting profile and placeholder defaults only fill unprovided fields
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.5**

- [x] 2. Implement POST /api/onboarding/skip API route
  - [x] 2.1 Create the skip endpoint with default profile creation and session setup
    - Add file for `POST /api/onboarding/skip` route
    - Validate Clerk JWT via `requireUserId()`
    - Accept optional `partialProfile` in request body (goal, deadline, daily_availability, overall_level)
    - Merge partial data with defaults: goal → "exploring", deadline → null, daily_availability → "1 hour", overall_level → "beginner"
    - Upsert CoreProfile with `profile_status: "skipped"` using existing `CoreProfileRepo.upsert()`
    - Do NOT create any Skill Graph documents
    - Create a new chat session and return `{ ok: true, sessionId }` on success
    - Return `{ ok: false, error: "..." }` with status 500 on DB failure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.1, 7.3, 7.4, 7.5_

  - [ ]* 2.2 Write property test for skip endpoint data state (Property 3)
    - **Property 3: Skip creates correct data state**
    - Generate random valid user IDs
    - Verify that after calling the skip handler, CoreProfile has `profile_status: "skipped"` and zero Skill Graph documents exist for that user
    - **Validates: Requirements 3.1, 3.5**

  - [ ]* 2.3 Write property test for partial response merging (Property 7)
    - **Property 7: Partial responses override defaults**
    - Generate random combinations of partial profile fields
    - Call the skip handler with partial data and verify user-provided values override defaults while missing fields get placeholders
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.5**

- [x] 3. Implement context assembler degraded mode
  - [x] 3.1 Add skipped-onboarding addendum and graceful degradation to context assembler
    - Modify the existing context assembler service
    - When `profile_status === "skipped"`: append the `SKIPPED_ONBOARDING_ADDENDUM` string to the system prompt
    - When `profile_status === "skipped"`: omit Skill Graph layer entirely (no nodes exist)
    - When `profile_status === "skipped"`: omit Episodic Memory layer entirely
    - When any Core Profile field is missing/null: omit that field from assembled context without erroring
    - When all profile fields are missing: assemble context using only system prompt + addendum + conversation window (last 6 turns)
    - Never throw an error due to missing profile data — always succeed
    - _Requirements: 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.2 Write property test for context assembly degradation (Property 4)
    - **Property 4: Context assembly degrades gracefully for skipped profiles**
    - Generate random subsets of profile fields (all 2^3 combinations of goal, deadline, availability) × random conversation histories
    - Verify: (a) addendum is present, (b) skill graph and episodic memory omitted, (c) conversation window included, (d) no errors thrown
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**

- [x] 4. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement SkipButton component
  - [x] 5.1 Create SkipButton component in the onboarding top navigation
    - Create `SkipButton` component with `onSkip` callback prop
    - Use outline/text-only variant from existing button system
    - Render inside the `.onb-top` container alongside the progress indicator
    - Ensure button is keyboard-focusable with `aria-label="Skip"`
    - Display label "Skip" with font size no larger than primary action elements
    - Enable the button across all 4 onboarding phases (Goal & Timeline, Current State, File Upload, Availability)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 5.2 Write property test for skip button across phases (Property 1)
    - **Property 1: Skip button present across all onboarding phases**
    - Generate random phase index (0–3)
    - Render onboarding at that phase and verify skip button is present, enabled, keyboard-focusable, with accessible name "Skip"
    - **Validates: Requirements 1.1, 1.4, 1.5**

- [x] 6. Implement SkipConfirmationDialog component
  - [x] 6.1 Create confirmation dialog with confirm/cancel actions and overlay
    - Create `SkipConfirmationDialog` component
    - Render a modal overlay/backdrop that blocks pointer events on the onboarding conversation below
    - Two actions: "Skip Setup" (confirm) and "Go Back" (cancel)
    - Show loading state on confirm button while skip API call is in progress
    - Trap keyboard focus within the dialog while open
    - On confirm: call `POST /api/onboarding/skip` with any partial profile data, then redirect to `/session/[id]` on success
    - On cancel: close dialog and return to onboarding at same position
    - On API error: show error message with retry option, do not redirect
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 6.2 Write property test for cancel preserving state (Property 2)
    - **Property 2: Cancel skip preserves conversation state**
    - Generate random message arrays (0–N messages) and random input field content
    - Open dialog then cancel; verify conversation thread, input content, and scroll position are identical to pre-dialog state
    - **Validates: Requirements 2.5**

- [x] 7. Implement OnboardingBanner component
  - [x] 7.1 Create the onboarding reminder banner for the chat interface
    - Create `OnboardingBanner` component
    - Display above the chat message area without overlapping messages or input controls
    - Message text (≤120 chars): "Complete your profile to get personalized study plans and skill tracking."
    - Include "Complete Setup" link that navigates to the onboarding flow
    - Include a dismiss button (X icon or text)
    - On dismiss: set `sessionStorage.setItem('mentorman_banner_dismissed', 'true')` and hide banner
    - On mount: check `sessionStorage` — if dismissed, don't render
    - Only render when `profile_status === "skipped"`; remove from DOM when status is `"complete"`
    - Handle `sessionStorage` unavailability gracefully (always show banner if storage throws)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 8. Implement CompleteSetupSection on Settings page
  - [x] 8.1 Add "Complete Setup" section to Settings page for skipped users
    - Create `CompleteSetupSection` component
    - Only render when `profile_status === "skipped"`
    - Display a call-to-action button labeled "Complete Setup"
    - On button click: navigate user to the onboarding flow
    - Hide this section when `profile_status` changes to `"complete"`
    - _Requirements: 5.1, 5.6_

- [x] 9. Implement deferred onboarding flow logic
  - [x] 9.1 Add deferred onboarding routing that skips completed phases
    - Modify the onboarding flow to accept a `deferred` mode
    - On entry in deferred mode: read existing profile fields from the database
    - Skip phases whose corresponding fields already have non-placeholder values (goal ≠ "exploring", deadline ≠ null, availability ≠ "1 hour")
    - Begin at the first phase whose field is still placeholder or null
    - On completion: update `profile_status` from "skipped" to "complete", bootstrap Skill Graph, redirect to Chat Interface within 1 second
    - On abandon (navigate away without completing): keep `profile_status` as "skipped", return user to Settings page, do NOT create Skill Graph documents
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 7.2_

  - [ ]* 9.2 Write property test for deferred completion status transition (Property 5)
    - **Property 5: Deferred completion transitions status to "complete"**
    - Generate random valid onboarding completion payloads (goal, deadline, availability, overall_level)
    - Verify that completing the flow updates `profile_status` from "skipped" to "complete"
    - **Validates: Requirements 5.3**

  - [ ]* 9.3 Write property test for abandon preserving skipped status (Property 6)
    - **Property 6: Abandoning deferred onboarding preserves skipped status**
    - Generate random abandon points (phases 1–4)
    - Verify `profile_status` remains "skipped" and no Skill Graph documents are created
    - **Validates: Requirements 5.5**

  - [ ]* 9.4 Write property test for skipping completed phases (Property 8)
    - **Property 8: Deferred onboarding skips completed phases**
    - Generate random existing profile states with various non-placeholder field combinations
    - Verify the deferred flow starts at the first incomplete phase
    - **Validates: Requirements 7.2**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Wire components together and integrate flows
  - [x] 11.1 Integrate SkipButton and SkipConfirmationDialog into the Onboarding component
    - Import and render `SkipButton` inside the onboarding top bar across all phases
    - Wire `onSkip` to open `SkipConfirmationDialog`
    - Extract any partial profile data from the onboarding conversation state to pass to the skip API
    - Wire confirm action to call skip API and handle redirect/error states
    - Wire cancel action to dismiss dialog
    - _Requirements: 1.1, 2.1, 2.3, 2.5, 2.6, 7.1_

  - [x] 11.2 Integrate OnboardingBanner into the Chat Interface
    - Import `OnboardingBanner` into the Chat Interface / session layout
    - Fetch profile status and conditionally render banner
    - Wire "Complete Setup" link to navigate to deferred onboarding
    - Wire dismiss to update sessionStorage
    - Remove banner from DOM when profile status becomes "complete"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 11.3 Integrate CompleteSetupSection into the Settings page
    - Import `CompleteSetupSection` into the Settings page component
    - Fetch profile status and conditionally render the section
    - Wire button click to navigate to deferred onboarding flow
    - _Requirements: 5.1, 5.6_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–8)
- Unit tests validate specific examples and edge cases
- The existing `CoreProfileRepo.upsert()` is reused — no new collection needed
- Banner dismissal uses `sessionStorage` for lightweight session-scoped persistence
- Context assembler changes are backward-compatible: fully-onboarded users are unaffected
- Frontend is TypeScript/React; backend is TypeScript with Next.js-style API routes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 3, "tasks": ["3.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1", "7.1", "8.1"] },
    { "id": 5, "tasks": ["6.2", "9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3", "9.4", "11.1"] },
    { "id": 7, "tasks": ["11.2", "11.3"] }
  ]
}
```
