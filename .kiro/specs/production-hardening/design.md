# Design — Production Hardening

## Overview

Strip developer/demo scaffolding from the React SPA and align the onboarding backend so the deadline is a real date. The real-data fetch paths already exist (`/api/profile`, `/api/skills`, `/api/sessions`, `/api/sessions/{id}`); this work removes the demo overlays and the dev-only chrome, fixes the boot state, and adds empty states.

## Current state (researched)

| Element | Today | Action |
|---|---|---|
| `Launcher` (app.tsx) | floating screen-jumper | **remove** |
| `TweaksPanel` (app.tsx + tweaks.tsx) | live theme editor | **remove**, bake defaults |
| `activeSession` initial | `'s1'` (seed) | **`'new'`** (fresh real session) |
| `SEEDS` / `SESSIONS` / `TOPICS` (data.ts) | fake chat/list/skills | **remove**; screens already fetch real data |
| `EvalPanel` / `MobileChat` (screens.tsx) | demo-only, no backend | **remove from nav** (only reachable via Launcher) |
| `daysLeft()` (ui.tsx, dashboard.tsx) | `new Date(freeText)` → NaN | **guard NaN → null** |
| onboarding `deadline` | free text ("3 months") | backend emits **`YYYY-MM-DD`** (today-relative) |

## Key decisions

| Decision | Rationale |
|---|---|
| Remove Demo_Screens from navigation rather than build backends | Evaluation/Mobile-preview have no backend; shipping them as fake demos is worse than omitting. Keeping them out of nav is the honest, minimal change. |
| Bake accent/tone defaults, drop the panel | Preserves the exact current look (accent `#34d399`, tone `balanced`) with no user-facing theming surface. |
| Boot to `'new'` session, not `'s1'` | A real user should land in a live mentor session (or onboarding if no profile), never a seeded demo. |
| Deadline as ISO date in the backend prompt | Matches the original Next prompt (`${TODAY}` interpolation); makes `daysLeft` correct. UI still guards NaN defensively. |
| Add Empty_States | New users have no sessions/skills; empty states keep the UI intentional. |

## Changes by file

**Frontend**
- `app.tsx`: remove `Launcher` component + render; remove `TweaksPanel` block; replace `useTweaks(...)` with constant `t = { accent: '#34d399', tone: 'balanced', density: 'cozy' }` (keep the accent `:root` effect); remove `EvalPanel`/`MobileChat`/`mobileOpen` and the `evaluation` view + mobile rendering; `activeSession` initial `'new'`; drop now-unused imports.
- `chat.tsx`: remove the `SEEDS` seed branch (keep localStorage-resume + API-load + auto-greet); resolve the active session's title/category from real session data / the new-session title instead of the `SESSIONS` mock.
- `ui.tsx`: `daysLeft` returns null when `Number.isNaN`; sidebar Empty_State when no sessions.
- `dashboard.tsx`: `daysLeft`/`weeksLeft`/`deadlineText` guard NaN; Empty_State when no skills.
- `screens.tsx`: remove `EvalPanel`, `MobileChat`, and their `EVAL_SEED`/`SEEDS` usage (Demo_Screens).
- `data.ts`: delete `SEEDS`, `SESSIONS`, `TOPICS`, `EVAL_SEED`, `EVAL_DONE_EXTRA`, and `mentorSystemPrompt` if unused; keep `MODES`, `ACCENTS`, `catToMode`, and type exports.

**Backend**
- `app/prompts/onboarding.md`: instruct the model to output `deadline` as `YYYY-MM-DD`.
- `app/services/prompt_store.py` `get_onboarding_prompt()`: append today's date so the model can compute an absolute date (parity with the Next `${TODAY}` interpolation).

## Testing

- Backend: a unit test asserting `get_onboarding_prompt()` includes today's date and the `YYYY-MM-DD` instruction; full suite stays green.
- Frontend: `tsc -b && vite build` clean; bundle scan shows no seed strings (e.g. "BFS/DFS warmups", "IAM roles for cross-account").
- Manual (user): fresh load lands in a real session/onboarding (no seeded chat); deadline shows real days; no launcher/tweaks; dashboard/sidebar show real data or empty states.
