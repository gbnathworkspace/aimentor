# Implementation Plan — Production Hardening

Backend changes are test-first; frontend is manually verified (project convention). Checkpoints are stop-and-verify gates.

## Tasks

- [x] 1. Backend: deadline as a real date
  - [x] 1.1 Instruct onboarding to emit `YYYY-MM-DD`
    - Update `app/prompts/onboarding.md` completion block to require `deadline` as `YYYY-MM-DD`
    - _Requirements: 3.1_
  - [x] 1.2 Inject today's date into the onboarding prompt
    - `get_onboarding_prompt()` appends today's date so the model computes an absolute date (parity with Next `${TODAY}`)
    - _Requirements: 3.1_
  - [x]* 1.3 Unit test
    - Assert `get_onboarding_prompt()` contains today's date and the `YYYY-MM-DD` instruction
    - **Validates: Requirement 3.1**

- [x] 2. Frontend: remove dev launcher + tweaks panel
  - [x] 2.1 Remove `Launcher` (component + render) from `app.tsx`
    - _Requirements: 1.1, 1.2_
  - [x] 2.2 Remove `TweaksPanel`; bake constant accent/tone defaults; keep the `:root` accent effect
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Frontend: remove demo screens + seed data
  - [x] 3.1 Remove `EvalPanel`, `MobileChat` and the `evaluation`/mobile rendering from `app.tsx` + `screens.tsx`
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 3.2 Remove the `SEEDS` branch from `chat.tsx`; resolve session title/category from real data; boot `activeSession` to `'new'`
    - _Requirements: 4.2, 4.3_
  - [x] 3.3 Delete `SEEDS`/`SESSIONS`/`TOPICS`/`EVAL_SEED`/`EVAL_DONE_EXTRA` from `data.ts` (keep config + types)
    - _Requirements: 4.1, 7.3_

- [~] 4. Frontend: fix NaN days + empty states
  - [x] 4.1 Guard `daysLeft`/`weeksLeft`/`deadlineText` against NaN (ui.tsx, dashboard.tsx)
    - _Requirements: 3.2, 3.3, 3.4_
  - [~] 4.2 Add Empty_States — DEFERRED (no crash on empty; polished empty-state copy pending)
    - _Requirements: 6.1, 6.2, 6.4_

- [ ] 5. Checkpoint - build + bundle scan
  - `tsc -b && vite build` clean; backend suite green; bundle has no seed strings. Then user verifies in browser.
