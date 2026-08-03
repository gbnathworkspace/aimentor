# Requirements Document

## Introduction

This specification covers migrating the MentorMan frontend from **Next.js (App Router)** to a **standalone React Single-Page Application (Vite + React + React Router)** that talks **directly to the unified FastAPI backend** on port 8000. The Next.js server tier — its API routes, direct MongoDB access, server-side Clerk auth, secret injection, token-budget logic, and file-upload handling — is removed. All of that server work consolidates into the existing `unified-backend` (FastAPI), completing the direction begun in the `backend-consolidation` spec.

The visual layer (React components, screens, and styles) must be preserved with **zero user-visible change**. Look, feel, layout, and behavior remain identical. The migration is architectural, not cosmetic.

### Confirmed Decisions (resolved during requirements review)

| Decision | Choice |
|---|---|
| Build stack | **Vite + React + React Router + TypeScript** (npm) |
| New SPA location | **New directory `mentorman-web/`** (Next app retained until parity verified, then removed) |
| Auth mechanism | **FastAPI verifies the Clerk session JWT networklessly against Clerk's JWKS**; user id from `sub` |
| Production hosting | **FastAPI serves the SPA static build** (same origin → CORS only required for local dev) |
| Mentor canonical behavior | **Match the current Next.js route: `claude-sonnet-4-6`, `max_tokens: 1024`**, plus the ported Token_Budget |
| SSR | **Not used** (authenticated app, no SEO need) |
| UI components | **Unchanged** — human-authored shadcn/ui components are moved verbatim from the Next shell to the React (Vite) shell; framework swap only, no redesign |

### Non-Goals (explicitly out of scope)

- **No UI changes.** Components, layout, styles, copy, and interactions stay byte-for-byte identical. This is a framework swap of the shell around the existing UI, nothing more.
- **No new features from the design docs.** The `design docs/` and `design_decisions/` folders are background context only. Designed-but-unbuilt items (e.g. the SSE **streaming** chat in `streaming-hld.md`, nudges, live skill_update events) are NOT implemented here.
- **No model/behavior "improvements."** Mentor stays at the implemented `claude-sonnet-4-6` / `max_tokens 1024` (not the HLD's `opus-4-6`/SSE design).
- **No redesign of backend domain logic** beyond what parity + Direct_Auth require.

### Streaming readiness (forward-compat only, not implemented)

Because SSE streaming is a known future feature, the migration SHALL avoid choices that block it: per the streaming HLD's own note, the API_Client SHALL use `fetch` + `ReadableStream` (which can send the `Authorization` header) rather than `EventSource` (which cannot). No streaming endpoint or `useStream` hook is built in this migration.

A central constraint is **behavioral parity**: today the Next.js app still implements most logic itself (direct DB repos, its own context assembler with `tiktoken` token budgeting, direct Anthropic calls), while the FastAPI backend holds a *parallel* implementation that has drifted (no token budgeting, different `max_tokens`). Parity must be restored in the backend **before** the Next.js implementation is decommissioned.

## Glossary

- **React_SPA**: The new Vite + React + React Router single-page application that replaces `mentorman-app` (Next.js). Builds to static assets; runs entirely in the browser.
- **FastAPI_Backend**: The existing `unified-backend` FastAPI service on port 8000. Becomes the single backend the React_SPA calls directly.
- **Clerk_JWT**: The Clerk **session token** (from `getToken()`) carried by the React_SPA in the `Authorization: Bearer <token>` header. Verified networklessly against Clerk's JWKS.
- **Direct_Auth**: The confirmed authentication model in which the browser sends the Clerk_JWT directly to the FastAPI_Backend, which verifies its signature **networklessly against Clerk's cached JWKS** and reads the user id from the `sub` claim. Replaces the legacy service-to-service `X-Api-Key` shared secret plus trusted `X-User-Id` header.
- **API_Client**: The typed fetch/axios layer in the React_SPA that calls FastAPI_Backend endpoints, attaching the Clerk_JWT. Replaces the Next.js `app/api/*` routes and `lib/api-proxy.ts`.
- **Token_Budget**: The `tiktoken`-based logic (currently `mentorman-app/lib/context-assembler/token-budget.ts`) that prioritizes core context and truncates immediate context to fit a token ceiling. Must be ported to the Python `context_assembler`.
- **Parity_Set**: The set of 12 backend endpoints whose behavior must match the current Next.js implementation before decommissioning: profile, skills (+ `{topic}`), sessions (+ `{sessionId}`), mentor, onboarding/chat, onboarding/complete, session upload (+ status), me, health.
- **Clerk**: The third-party authentication provider.

## Requirements

### Requirement 1: React SPA Project Scaffold

**User Story:** As a developer, I want a Vite + React + React Router project, so that the frontend builds to static assets with no Node server at runtime.

#### Acceptance Criteria

1. THE React_SPA SHALL be a Vite project using React and TypeScript
2. THE React_SPA SHALL use React Router for client-side routing
3. THE React_SPA SHALL produce a static build (HTML/CSS/JS) via a `build` script with no server-side runtime dependency
4. THE React_SPA SHALL run a dev server with hot-module reload via a `dev` script
5. THE React_SPA SHALL configure the FastAPI base URL from a build-time environment variable (`VITE_API_BASE`)

### Requirement 2: Visual and Functional Parity

**User Story:** As a user, I want the migrated app to look and behave exactly as before, so that nothing about my experience changes.

#### Acceptance Criteria

1. THE React_SPA SHALL reuse the existing human-authored shadcn/ui components (`components/mentorman/*`, screens, UI) **verbatim** — only import paths and framework-specific wrappers may change, never markup, classes, or styles
2. THE React_SPA SHALL preserve `globals.css` and all existing styling so rendered output is pixel-equivalent
3. WHEN a user performs any flow available today (onboarding, chat, session review, file upload), THE React_SPA SHALL produce the same observable behavior
4. THE React_SPA SHALL NOT introduce server-side rendering; all rendering occurs in the browser
5. THE migration SHALL NOT redesign, restyle, or add UI; any component change beyond framework wiring is out of scope

### Requirement 3: Client-Side Routing Parity

**User Story:** As a user, I want all current pages and URLs to keep working, so that navigation and links are unchanged.

#### Acceptance Criteria

1. THE React_SPA SHALL serve the main application at the root route `/`
2. THE React_SPA SHALL provide sign-in and sign-up routes equivalent to the current `(auth)/sign-in` and `(auth)/sign-up`
3. THE React_SPA SHALL support dynamic session routes equivalent to the current `[sessionId]` segments
4. WHEN an unauthenticated user navigates to a protected route, THE React_SPA SHALL redirect to the sign-in route
5. WHEN the static host receives a deep-link path, THE React_SPA SHALL fall back to `index.html` so client routing resolves it (SPA fallback)

### Requirement 4: Clerk Authentication in the SPA

**User Story:** As a user, I want to sign in with Clerk in the React app, so that my identity and session work as before.

#### Acceptance Criteria

1. THE React_SPA SHALL integrate `@clerk/clerk-react` for authentication
2. THE React_SPA SHALL gate protected routes behind an authenticated Clerk session
3. WHEN making an API call, THE React_SPA SHALL attach the current Clerk_JWT as an `Authorization: Bearer` header
4. IF the Clerk session is absent or expired, THEN THE React_SPA SHALL prompt re-authentication rather than calling the backend
5. THE React_SPA SHALL read the Clerk publishable key from `VITE_CLERK_PUBLISHABLE_KEY`

### Requirement 5: Backend Clerk JWT Verification (Direct_Auth)

**User Story:** As a developer, I want the FastAPI_Backend to verify Clerk tokens itself, so that the browser can call it directly without a Node proxy or shared secret.

#### Acceptance Criteria

1. THE FastAPI_Backend SHALL accept a Clerk_JWT in the `Authorization: Bearer` header on protected endpoints
2. THE FastAPI_Backend SHALL verify the Clerk_JWT signature **networklessly** against Clerk's published JWKS (fetched once and cached; no per-request call to Clerk), reading the issuer/JWKS location from configuration (`CLERK_ISSUER` / `CLERK_JWKS_URL`)
3. WHEN a Clerk_JWT is valid, THE FastAPI_Backend SHALL derive the user id from the token `sub` claim and scope all data access to it
4. IF the Authorization header is missing, malformed, or the token fails verification, THEN THE FastAPI_Backend SHALL return HTTP 401
5. THE FastAPI_Backend SHALL no longer require the legacy `X-Api-Key` shared secret nor a client-supplied `X-User-Id` for browser requests
6. THE FastAPI_Backend SHALL NOT expose `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, or any server secret to the client

### Requirement 6: CORS for Local Development

**User Story:** As a developer, I want the backend to permit the local Vite dev server's cross-origin requests, so that I can develop the SPA against FastAPI. (In production the SPA is same-origin — served by FastAPI — so CORS is not exercised there.)

#### Acceptance Criteria

1. THE FastAPI_Backend SHALL enable CORS for the configured development origin(s) (e.g. the Vite dev server)
2. THE FastAPI_Backend SHALL allow the `Authorization` and `Content-Type` request headers
3. THE FastAPI_Backend SHALL allow the HTTP methods used by the Parity_Set (GET, POST, PUT, DELETE, OPTIONS)
4. THE FastAPI_Backend SHALL read allowed origins from configuration (`CORS_ORIGINS`) rather than hard-coding them
5. WHEN the SPA is served same-origin in production, THE configuration SHALL NOT require any cross-origin allowance for it

### Requirement 7: Typed API Client

**User Story:** As a developer, I want a single typed client for backend calls, so that components stop depending on Next.js API routes.

#### Acceptance Criteria

1. THE API_Client SHALL provide functions covering every endpoint in the Parity_Set
2. THE API_Client SHALL attach the Clerk_JWT to every request automatically
3. THE API_Client SHALL target `VITE_API_BASE` as the backend origin
4. WHEN the backend returns a non-2xx status, THE API_Client SHALL surface a typed error to the caller
5. THE React_SPA components SHALL call the API_Client instead of relative `/api/*` paths

### Requirement 8: Backend Endpoint Parity for the Parity_Set

**User Story:** As a user, I want every feature that the Next.js routes provided to keep working through FastAPI, so that no functionality is lost.

#### Acceptance Criteria

1. THE FastAPI_Backend SHALL expose equivalents for all Parity_Set endpoints with the same response shapes the React_SPA consumes
2. WHEN the React_SPA requests profile, skills, sessions, mentor, or onboarding data, THE FastAPI_Backend SHALL return results equivalent to the current Next.js implementation
3. THE FastAPI_Backend SHALL provide a `me` endpoint returning the authenticated user's identity/profile bootstrap data
4. IF a Parity_Set endpoint is missing from the backend, THEN it SHALL be implemented before the corresponding Next.js route is removed
5. THE migration SHALL verify each Parity_Set endpoint against its Next.js counterpart before decommissioning

### Requirement 9: Mentor Behavioral Parity (Token_Budget Port)

**User Story:** As a user, I want mentor responses to be the same quality as before, so that moving the logic to Python does not change answers.

#### Acceptance Criteria

1. THE FastAPI_Backend `context_assembler` SHALL implement Token_Budget enforcement equivalent to the Next.js `token-budget.ts`
2. THE FastAPI_Backend SHALL prioritize core context (system prompt + L1 profile + L2 skill graph) and never drop it under budget pressure
3. THE FastAPI_Backend SHALL truncate immediate/episodic context to fit the token ceiling, matching the Next.js priority order
4. THE FastAPI_Backend mentor endpoint SHALL use the same `max_tokens` and model configuration as the current Next.js mentor route, unless a change is explicitly approved
5. WHEN given identical inputs, THE FastAPI_Backend mentor endpoint SHALL produce context assembly equivalent to the Next.js implementation

### Requirement 10: File Upload Direct to FastAPI

**User Story:** As a user, I want to upload session files and see processing status, so that ingestion works without the Next.js upload route.

#### Acceptance Criteria

1. THE React_SPA SHALL upload files directly to the FastAPI_Backend upload endpoint as multipart form data with the Clerk_JWT attached
2. THE FastAPI_Backend SHALL accept the upload, start background processing, and return a job identifier
3. THE React_SPA SHALL poll the FastAPI_Backend job-status endpoint until processing completes or fails
4. WHEN processing fails, THE React_SPA SHALL surface the failure state to the user
5. THE upload flow SHALL preserve the file types and size limits enforced today

### Requirement 11: Environment Variable Migration

**User Story:** As a developer, I want client and server configuration cleanly separated, so that secrets never reach the browser.

#### Acceptance Criteria

1. THE React_SPA SHALL only read variables prefixed `VITE_` (e.g. `VITE_API_BASE`, `VITE_CLERK_PUBLISHABLE_KEY`)
2. THE FastAPI_Backend SHALL retain all secrets (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `MONGODB_URI`, `CLERK_SECRET_KEY`) server-side only
3. THE legacy `NEXT_PUBLIC_*` and `MENTORMAN_API_KEY` client variables SHALL be removed from the frontend
4. THE migration SHALL document the new env var set in a `.env.example` for the React_SPA

### Requirement 12: No Secrets in the Client Bundle

**User Story:** As a security reviewer, I want assurance that the shipped JavaScript contains no secrets, so that publishing the SPA is safe.

#### Acceptance Criteria

1. THE React_SPA production bundle SHALL NOT contain `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `MONGODB_URI`, `CLERK_SECRET_KEY`, or `MENTORMAN_API_KEY`
2. THE React_SPA SHALL only embed the Clerk publishable key and the API base URL, both non-secret
3. THE migration SHALL include a build-time check or review step that scans the bundle for forbidden secret patterns

### Requirement 13: Build and Deployment (FastAPI serves the SPA)

**User Story:** As an operator, I want FastAPI to serve the built SPA, so that there is a single same-origin deployment and the Node tier is gone.

#### Acceptance Criteria

1. THE React_SPA SHALL build to a static directory that THE FastAPI_Backend serves as static files (single origin for app + API)
2. THE FastAPI_Backend SHALL serve `index.html` as the fallback for unmatched non-API GET paths, so client-side routing resolves deep links (SPA fallback)
3. THE FastAPI_Backend SHALL continue to route `/api/*` and `/health` to the API, taking precedence over the static fallback
4. WHEN built for same-origin production, THE React_SPA `VITE_API_BASE` SHALL be a relative base (no cross-origin host required)
5. THE local development setup SHALL still support the Vite dev server calling FastAPI cross-origin via `CORS_ORIGINS`

### Requirement 14: Decommission the Next.js App

**User Story:** As a developer, I want the obsolete Next.js code removed after parity is confirmed, so that there is a single frontend and single backend.

#### Acceptance Criteria

1. WHEN all Parity_Set endpoints are verified against the Next.js implementation, THE migration SHALL remove the Next.js `app/api/*` routes
2. THE migration SHALL remove now-dead frontend server code (`lib/db/*`, `lib/api-proxy.ts`, `lib/auth.ts` server helpers, `lib/context-assembler` once ported, `proxy.ts`, `instrumentation*.ts`, `next.config.ts`)
3. THE migration SHALL remove Next.js and Clerk-Next dependencies from the frontend package manifest
4. THE migration SHALL NOT remove any Next.js code until its FastAPI equivalent is verified (no loss of working functionality)
