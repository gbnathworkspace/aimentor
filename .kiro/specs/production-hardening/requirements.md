# Requirements Document — Production Hardening

## Introduction

The migrated React SPA still carries developer/demo scaffolding from the original prototype: a "jump to screen" dev launcher, a live "tweaks" theming panel, hardcoded seed conversations and mock skill/session data, demo-only screens with no backend (Evaluation, Mobile preview), and a `NaN days` bug from a non-date deadline. This spec removes that scaffolding and wires every user-facing screen to real data so the app is production-ready: a real user sees only their own profile, skill graph, sessions, and mentor conversations.

## Glossary

- **Dev_Launcher**: The floating "screens" / "JUMP TO SCREEN" widget that jumps directly to any screen. Developer navigation only.
- **Tweaks_Panel**: The floating "tweaks" panel for live-editing accent colour / tone / density. Demo tool.
- **Seed_Data**: Hardcoded sample content in `data.ts` — `SEEDS` (fake chat), `SESSIONS` (fake sidebar list), `TOPICS` (fake skill graph), `EVAL_SEED`/`EVAL_DONE_EXTRA` (fake evaluation).
- **Demo_Screen**: A screen with no backend support, currently driven entirely by Seed_Data: Evaluation (`EvalPanel`) and Mobile preview (`MobileChat`).
- **Real_Data**: Data fetched from the FastAPI backend for the authenticated user (profile, skills, sessions, messages).
- **Empty_State**: The UI shown when a Real_Data collection is empty (no sessions yet, no skills yet).

## Requirements

### Requirement 1: Remove the developer launcher

**User Story:** As a product owner, I want the dev screen-jumper gone, so that users navigate only through real app flows.

#### Acceptance Criteria
1. THE app SHALL NOT render the Dev_Launcher in any build.
2. THE app SHALL reach screens only through normal user flow (sign-in, onboarding, chat, dashboard, settings, session end).
3. WHEN the Dev_Launcher code is removed, THE build SHALL still compile and all reachable screens SHALL function.

### Requirement 2: Remove the tweaks panel

**User Story:** As a product owner, I want the demo theming panel gone, so that the app ships a single consistent look.

#### Acceptance Criteria
1. THE app SHALL NOT render the Tweaks_Panel.
2. THE app SHALL apply a single baked-in default accent and tone (the current defaults: accent `#34d399`, tone `balanced`).
3. THE removal SHALL NOT change the default visual appearance of any production screen.

### Requirement 3: Fix the deadline ("NaN days")

**User Story:** As a user, I want my deadline shown correctly, so that I never see "NaN days".

#### Acceptance Criteria
1. THE onboarding backend SHALL emit `deadline` as an ISO `YYYY-MM-DD` date, computing it from today when the user states a relative timeframe ("3 months").
2. THE UI deadline helpers SHALL treat an unparseable deadline as "no deadline" (return null) rather than rendering `NaN`.
3. WHEN a valid deadline exists, THE UI SHALL show the correct days/weeks remaining.
4. WHEN no valid deadline exists, THE UI SHALL omit the "days left" text entirely.

### Requirement 4: Remove seed/mock data and boot into real state

**User Story:** As a user, I want to see only my own data, so that nothing fake appears.

#### Acceptance Criteria
1. THE app SHALL NOT render Seed_Data anywhere.
2. THE chat SHALL load messages for an existing session from the backend, and start a fresh session via the live mentor greeting — never from hardcoded seeds.
3. THE app SHALL NOT boot into a hardcoded session id; a returning user with sessions SHALL resume/list real sessions, and a new user SHALL start a fresh session.
4. THE sidebar session list and dashboard skill graph SHALL render only Real_Data.

### Requirement 5: Honest handling of backend-less screens

**User Story:** As a user, I don't want to land in a fake demo, so that every screen I reach is real.

#### Acceptance Criteria
1. THE app SHALL NOT present a Demo_Screen (Evaluation, Mobile preview) as a working feature when it has no backend.
2. THE Demo_Screens SHALL be removed from production navigation (they were reachable only via the Dev_Launcher).
3. IF a Demo_Screen's code is retained, THEN it SHALL NOT be reachable through any production flow.

### Requirement 6: Real-data screens with empty states

**User Story:** As a new user with no data yet, I want clear empty states, so that the app looks intentional, not broken.

#### Acceptance Criteria
1. THE dashboard SHALL render the user's real skill graph; WHEN there are no skills, it SHALL show a clear Empty_State.
2. THE sidebar SHALL render the user's real sessions; WHEN there are none, it SHALL show a clear Empty_State.
3. THE settings/profile screen SHALL render the user's real profile fields (goal, deadline, level, availability) from the backend.
4. THE app SHALL NOT crash or render `undefined`/`NaN`/`null` literals when a Real_Data collection is empty.

### Requirement 7: Build and parity integrity

**User Story:** As a developer, I want the cleanup to keep the app working, so that no regressions ship.

#### Acceptance Criteria
1. THE SPA SHALL build with no type errors after the cleanup.
2. THE backend test suite SHALL remain green.
3. THE production bundle SHALL contain no Seed_Data string content (fake titles, seed messages).
