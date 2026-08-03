# Implementation Plan: Frontend React Migration (React + FastAPI)

## Overview

Migrate the MentorMan frontend from Next.js to a Vite + React + React Router SPA that calls the `unified-backend` FastAPI directly. Move authentication to Clerk JWT verification inside FastAPI, add CORS, restore backend behavioral parity (Token_Budget port), then migrate the UI per-domain and decommission the Next.js server tier only after each domain is verified.

Tasks marked `[ ]*` are optional automated tests. Per project convention: backend gets strict TDD; frontend is manually verified. "Checkpoint" tasks are stop-and-verify gates.

## Tasks

- [x] 1. Backend: enable direct browser access (auth + CORS)
  - [x] 1.1 Add CORS middleware to FastAPI (dev origin only)
    - Add `CORSMiddleware` in `app/main.py`, allowing `Authorization`/`Content-Type` headers and GET/POST/PUT/DELETE/OPTIONS
    - Add `CORS_ORIGINS` to `app/config/settings.py` (comma-separated → list); scope to the Vite dev origin (prod is same-origin)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x] 1.2 Implement Clerk JWT verification dependency (networkless JWKS)
    - In `app/core/security.py`, add a `require_user` dependency that reads `Authorization: Bearer` (Clerk session token), verifies the signature against **cached** Clerk JWKS with no per-request network call, and returns `user_id` from `sub`
    - Fetch + cache JWKS at startup; add `CLERK_ISSUER`/`CLERK_JWKS_URL` to settings
    - Return 401 on missing/malformed/expired/invalid token
    - Keep the legacy `X-Api-Key`/`X-User-Id` path available behind a transition flag
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - [x]* 1.3 Property test: JWT auth enforcement
    - **Property: Auth Enforcement** — random endpoints × token states (valid/expired/tampered/missing) → 401 except valid
    - **Validates: Requirements 5.1, 5.2, 5.4**

- [x] 2. Checkpoint - Backend accepts a real Clerk JWT
  - Verified: /health ok; 401 without auth; 401 with bad bearer; CORS preflight allows dev origin; JWKS reachable for networkless verify. Live signed-in 200 deferred to Task 8 (needs a browser session).

- [x] 3. Backend: restore mentor behavioral parity
  - [x] 3.1 Port Token_Budget into the Python context assembler
    - Implement token-budget enforcement in `app/services/context_assembler.py` mirroring `mentorman-app/lib/context-assembler/token-budget.ts` (core context never dropped; immediate/episodic truncated to ceiling in the same priority order)
    - _Requirements: 9.1, 9.2, 9.3, 9.5_
  - [x] 3.2 Align mentor generation config to canonical values
    - Set the mentor endpoint to `model: claude-sonnet-4-6`, `max_tokens: 1024` (matching the current Next.js route), correcting the drifted `claude-sonnet-4-20250514` / 4096
    - _Requirements: 9.4_
  - [x]* 3.3 Property test: token budget invariants
    - **Property: Budget Priority** — core context always present; total tokens ≤ ceiling; truncation order matches TS impl
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [x] 4. Backend: close Parity_Set gaps
  - [x] 4.1 `/api/me` resolved client-side (Clerk), not a backend endpoint
    - Default Clerk session JWT has no name/email; networkless backend can't produce them. API_Client `me()` reads Clerk `useUser()` instead. No backend endpoint added.
    - _Requirements: 8.3_
  - [x] 4.2 Parity-verify profile, skills, sessions, onboarding shapes
    - Catalogued: FastAPI returns camelCase + accepts snake_case input; frozen UI is snake_case. Resolution = API_Client normalizes responses camel→snake (built in Task 7). Backend contract unchanged.
    - _Requirements: 8.1, 8.2, 8.4, 8.5_
  - [ ]* 4.3 Parity harness tests for the Parity_Set
    - DEFERRED (logged, not silent): a cross-implementation harness needs both stacks against one DB. Parity is instead enforced by the documented shape mapping + the API_Client casing adapter, and proven by end-to-end manual verification at Task 8.
    - **Validates: Requirements 8.1, 8.2, 8.5**

- [x] 5. Checkpoint - Backend at parity
  - Backend parity established: auth+CORS, Token_Budget port, casing adapter plan, client-side me(). 154 backend tests green. Proceeding to frontend under the user's "complete full migration" directive.

- [x] 6. Frontend: scaffold the React SPA
  - [x] 6.1 Create the Vite + React + TypeScript project in `mentorman-web/`
    - New SPA project at `mentorman-web/` (npm) with `dev` and `build` scripts; configure `VITE_API_BASE` (`http://localhost:8000` in dev, relative `''` in same-origin prod) and `VITE_CLERK_PUBLISHABLE_KEY`
    - Add React Router; create `.env.example` for the SPA
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 11.1, 11.4_
  - [x] 6.2 Port presentational components and styles verbatim
    - Copy the human-authored shadcn/ui components (`components/mentorman/*`), `globals.css`, `public/*`; fix only import paths / framework wrappers — **no markup, class, style, or behavior change**
    - _Requirements: 2.1, 2.2, 2.4, 2.5_
  - [x] 6.3 Set up routing and Clerk provider
    - `App.tsx` with `<ClerkProvider>`, routes for `/`, `/sign-in`, `/sign-up`, and dynamic session routes; `<ProtectedRoute>` redirecting unauthenticated users
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.5_

- [x] 7. Frontend: API client and data wiring
  - [x] 7.1 Build the typed API_Client
    - `src/api/client.ts` using `fetch` + `ReadableStream` (not `EventSource`) that calls `getToken()` and attaches `Authorization: Bearer`; typed modules per domain; typed errors on non-2xx. Streaming-ready but no streaming endpoint built here.
    - _Requirements: 4.3, 4.4, 7.1, 7.2, 7.3, 7.4_
  - [x] 7.2 Replace `/api/*` calls in components with API_Client
    - Point all data reads/writes at `VITE_API_BASE` via the client; remove relative `/api/*` usage
    - _Requirements: 7.5_
  - [x] 7.3 Wire file upload + status polling directly to FastAPI
    - Multipart upload with JWT; poll job-status endpoint; surface failure state; preserve type/size limits
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 8. Checkpoint - Manual flow verification (frontend)
  - Run onboarding, chat, session review, and upload against FastAPI; visually confirm parity with the Next.js app. Ask the user to confirm before decommissioning.

- [x] 9. Hardening: secrets and deployment
  - [x] 9.1 Enforce client/server env separation
    - Confirm SPA reads only `VITE_*`; ensure all secrets remain server-side; remove `NEXT_PUBLIC_*`/`MENTORMAN_API_KEY` from the frontend
    - _Requirements: 11.1, 11.2, 11.3_
  - [x]* 9.2 Bundle secret scan
    - Build production bundle; grep for forbidden secret patterns (ANTHROPIC/VOYAGE/MONGODB/CLERK_SECRET/MENTORMAN_API_KEY) → must be absent
    - **Validates: Requirements 12.1, 12.2, 12.3**
  - [x] 9.3 Serve the SPA from FastAPI + build/deploy config
    - Mount the built SPA as static files in `app/main.py`; serve `index.html` as fallback for unmatched non-API GET paths, with `/api/*` and `/health` taking precedence
    - Build the SPA with relative `VITE_API_BASE` for same-origin prod; keep dev CORS origin for the Vite dev server
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [x] 10. Decommission the Next.js app
  - [x] 10.1 Remove Next.js API routes (only after parity verified)
    - Delete `mentorman-app/app/api/*`
    - _Requirements: 14.1, 14.4_
  - [x] 10.2 Remove dead frontend server code
    - Delete `lib/db/*`, `lib/api-proxy.ts`, server `lib/auth.ts`, `lib/context-assembler/*` (after port), `proxy.ts`, `instrumentation*.ts`, `next.config.ts`
    - _Requirements: 14.2_
  - [x] 10.3 Remove Next/Clerk-Next dependencies
    - Drop `next` and `@clerk/nextjs` from the frontend manifest; retire the Next project once the SPA is the sole frontend
    - _Requirements: 14.3_

- [x] 11. Final checkpoint
  - Single frontend (React SPA) + single backend (FastAPI), all flows verified, no secrets in bundle, Next.js removed. Confirmed complete.

## Notes

- Tasks marked with `*` are optional automated tests and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation before irreversible steps (e.g. decommissioning Next.js)
- Property tests validate universal correctness properties (JWT auth enforcement, token budget invariants)
- Backend gets strict TDD; frontend is verified manually per project convention
- Task 4.3 (parity harness) was deferred — parity is enforced by shape mapping + API_Client casing adapter, proven by manual end-to-end verification
- The `/api/me` endpoint was resolved client-side via Clerk `useUser()` rather than a backend endpoint (networkless-JWKS constraint)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["3.1", "3.2", "4.1", "4.2"] },
    { "id": 3, "tasks": ["3.3", "4.3"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["9.1", "9.2", "9.3"] },
    { "id": 9, "tasks": ["10.1"] },
    { "id": 10, "tasks": ["10.2", "10.3"] }
  ]
}
```
