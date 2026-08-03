# Implementation Plan: Self-Hosted Authentication

## Overview

Replace Clerk authentication with a fully self-hosted auth system built on FastAPI + MongoDB (backend) and React 19 (frontend). Implementation follows a bottom-up approach: core auth services first, then endpoints, then frontend, then Clerk removal.

## Tasks

- [x] 1. Set up auth module structure and dependencies
  - [x] 1.1 Create backend auth module directory structure and install dependencies
    - Create `unified-backend/app/auth/` directory with `__init__.py`
    - Add `bcrypt>=4.0.0` and `email-validator` to requirements.txt
    - Verify `pyjwt[crypto]`, `httpx`, `motor`, `pydantic-settings` already present
    - Add new auth settings to `app/config/settings.py` (JWT_SECRET, OAuth credentials, email config, LEGACY_AUTH_ENABLED default true)
    - _Requirements: 5.1, 6.5_

  - [x] 1.2 Create Pydantic request/response schemas
    - Create `app/auth/schemas.py` with RegisterRequest, LoginRequest, OTPRequestBody, OTPVerifyBody, TokenResponse, MessageResponse
    - Use EmailStr for email validation (RFC 5322), Field constraints for password (min_length=8, max_length=128)
    - _Requirements: 1.3, 1.5, 1.7, 3.8_

  - [x] 1.3 Create MongoDB collection indexes setup script
    - Create index setup for `users` (unique on user_id, unique on email)
    - Create index setup for `refresh_tokens` (unique on token, index on user_id, TTL on expires_at)
    - Create index setup for `otp_codes` (index on email, TTL on expires_at)
    - Create index setup for `oauth_states` (unique on state, TTL on expires_at)
    - Create index setup for `rate_limits` (compound on key+action+timestamp, TTL on expires_at)
    - _Requirements: 1.6, 5.3_

- [x] 2. Implement core auth services
  - [x] 2.1 Implement PasswordService (bcrypt hashing)
    - Create `app/auth/password_service.py` with `hash_password()` and `verify_password()`
    - Use bcrypt with work factor 12
    - _Requirements: 1.4, 2.1, 2.2_

  - [ ]* 2.2 Write property test for PasswordService
    - **Property 1: Password Hash Round-Trip**
    - **Validates: Requirements 1.4, 2.1, 2.2**

  - [x] 2.3 Implement TokenManager (JWT + refresh token lifecycle)
    - Create `app/auth/token_manager.py` with `create_access_token()`, `verify_access_token()`, `create_refresh_token()`, `rotate_refresh_token()`, `revoke_refresh_token()`, `revoke_all_user_tokens()`
    - Access tokens: HS256 JWT with sub, iat, exp claims, 15-minute expiry
    - Refresh tokens: opaque token_urlsafe(32), 7-day expiry, stored in MongoDB
    - Implement rotation detection (is_used flag) — if reused token detected, revoke all user tokens
    - _Requirements: 5.1, 5.2, 5.3, 5.7, 5.8, 5.9, 5.10_

  - [ ]* 2.4 Write property test for TokenManager
    - **Property 2: JWT Token Round-Trip**
    - **Validates: Requirements 5.1, 5.2, 5.4, 5.5**

  - [ ]* 2.5 Write property test for refresh token rotation
    - **Property 6: Refresh Token Rotation**
    - **Validates: Requirements 5.7, 5.8, 5.9**

  - [x] 2.6 Implement RateLimiter (sliding window)
    - Create `app/auth/rate_limiter.py` with `check_and_increment()` and `reset()`
    - Sliding window: 5 attempts per 15 minutes per key+action
    - Store attempts as individual documents with TTL auto-cleanup
    - _Requirements: 2.6, 3.6, 3.9_

  - [ ]* 2.7 Write property test for RateLimiter
    - **Property 4: Rate Limit Enforcement**
    - **Validates: Requirements 2.6, 3.6, 3.9**

  - [x] 2.8 Implement OTPService (generate, send, verify)
    - Create `app/auth/otp_service.py` with `generate_and_send()` and `verify()`
    - Generate cryptographically random 6-digit code via secrets.randbelow
    - Store with 10-minute TTL expiry, invalidate previous codes on new request
    - Delete code on successful verification (single-use)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 2.9 Write property test for OTP single-use
    - **Property 5: OTP Single-Use**
    - **Validates: Requirements 3.5**

  - [x] 2.10 Implement EmailSender abstraction
    - Create `app/auth/email_sender.py` with `send_otp_email()`
    - Console backend for development (logs code to stdout)
    - API backend for production (httpx POST to configured email provider)
    - _Requirements: 3.1_

  - [x] 2.11 Implement OAuthHandler (Google + GitHub)
    - Create `app/auth/oauth_handler.py` with `get_authorization_url()`, `handle_callback()`, `_exchange_code()`, `_fetch_user_info()`
    - Generate cryptographically random state parameter, store in MongoDB with 5-min TTL
    - Validate state on callback before exchanging code
    - Support Google (openid, email, profile scopes) and GitHub (user:email scope)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 3. Checkpoint - Core services verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement auth dependencies and router endpoints
  - [x] 4.1 Implement require_auth() and require_admin() FastAPI dependencies
    - Create `app/auth/dependencies.py` with `require_auth()` and `require_admin()`
    - Priority: Bearer JWT > Legacy headers (X-Api-Key + X-User-Id)
    - If Bearer token present and invalid → 401 (no fallback to legacy)
    - If no Bearer token and LEGACY_AUTH_ENABLED=true → accept valid legacy headers
    - If no Bearer token and LEGACY_AUTH_ENABLED=false → 401
    - Check is_active flag on user document for deactivated account (403)
    - require_admin() verifies is_admin flag from database
    - _Requirements: 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 9.3, 9.4, 9.5_

  - [ ]* 4.2 Write property test for legacy auth priority
    - **Property 9: Legacy Auth Priority**
    - **Validates: Requirements 6.2, 6.3**

  - [ ]* 4.3 Write property test for deactivated user rejection
    - **Property 7: Deactivated User Rejection**
    - **Validates: Requirements 9.2, 9.3**

  - [ ]* 4.4 Write property test for admin access control
    - **Property 8: Admin Access Control**
    - **Validates: Requirements 9.4, 9.5**

  - [x] 4.5 Implement auth router — registration and login endpoints
    - Create `app/auth/router.py` with POST /api/auth/register and POST /api/auth/login
    - Registration: validate email/password, check duplicate email (409), hash password, create user doc, issue tokens
    - Login: rate limit check, find user by email, verify password, issue tokens (or 401)
    - Same error body for wrong email vs wrong password (user enumeration prevention)
    - Reset rate limit counter on successful login
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 4.6 Write property test for registration uniqueness
    - **Property 3: Registration Uniqueness**
    - **Validates: Requirements 1.2**

  - [ ]* 4.7 Write property test for user enumeration prevention
    - **Property 10: User Enumeration Prevention**
    - **Validates: Requirements 2.4**

  - [ ]* 4.8 Write property test for input validation enforcement
    - **Property 12: Input Validation Enforcement**
    - **Validates: Requirements 1.3, 1.5, 1.7**

  - [x] 4.9 Implement auth router — OTP endpoints
    - Add POST /api/auth/otp/request and POST /api/auth/otp/verify to router
    - OTP request: rate limit check (5 requests/15min), validate email, generate+send OTP
    - OTP verify: rate limit check (5 attempts/15min), verify code, find-or-create user, issue tokens
    - Auto-register new email addresses on first OTP verification
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 4.10 Implement auth router — OAuth endpoints
    - Add GET /api/auth/oauth/{provider} and GET /api/auth/oauth/callback to router
    - Initiate: generate state, redirect to provider authorize URL
    - Callback: validate state, exchange code, fetch user profile, find-or-create user, link OAuth identity, issue tokens
    - Redirect to frontend /auth/callback?token=... on success
    - Redirect to /login?error=... on failure
    - Handle missing email from provider (redirect with error)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 4.11 Write property test for OAuth state CSRF protection
    - **Property 11: OAuth State CSRF Protection**
    - **Validates: Requirements 4.1, 4.5**

  - [x] 4.12 Implement auth router — refresh and logout endpoints
    - Add POST /api/auth/refresh and POST /api/auth/logout to router
    - Refresh: extract refresh token from HTTP-only cookie, rotate token pair, set new cookie
    - Logout: invalidate refresh token, clear cookie, return success
    - _Requirements: 5.7, 5.8, 5.9, 5.10_

  - [x] 4.13 Implement admin router — user management endpoints
    - Create `app/auth/admin_router.py` with GET /api/admin/users, POST /api/admin/users/{user_id}/deactivate, POST /api/admin/users/{user_id}/activate
    - List users: paginated (default 20, max 100), exclude hashed_password field
    - Deactivate: mark inactive, revoke all refresh tokens
    - Activate: mark active
    - All endpoints require admin dependency
    - _Requirements: 9.1, 9.2, 9.3, 9.6_

  - [x] 4.14 Register auth and admin routers in the FastAPI app
    - Mount auth router and admin router in the main FastAPI application
    - Replace existing Clerk-based `require_auth()` dependency with the new one across existing app routers
    - _Requirements: 5.4, 6.1_

- [x] 5. Checkpoint - Backend API verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement frontend auth system
  - [x] 6.1 Create AuthProvider context and useAuth hook
    - Create `mentorman-web/src/auth/AuthProvider.tsx` with token state management
    - Store access token in memory only (not localStorage/sessionStorage)
    - Implement silent refresh on mount (attempt token refresh from HTTP-only cookie)
    - Expose login(), logout(), refresh(), isAuthenticated, accessToken via context
    - Create `mentorman-web/src/auth/useAuth.ts` hook
    - _Requirements: 7.3_

  - [x] 6.2 Create api-client with auto-refresh on 401
    - Create `mentorman-web/src/auth/api-client.ts` with `apiFetch()` wrapper
    - Attach Bearer token to all requests from in-memory state
    - On 401 response: attempt exactly one token refresh, retry original request
    - If refresh fails: clear token, redirect to login
    - Send credentials: 'include' for cookie-based refresh
    - _Requirements: 7.5, 7.6_

  - [x] 6.3 Create ProtectedRoute component
    - Create `mentorman-web/src/auth/ProtectedRoute.tsx`
    - Redirect unauthenticated users to /login with return path preserved in state
    - _Requirements: 7.4_

  - [x] 6.4 Create LoginPage component
    - Create `mentorman-web/src/auth/LoginPage.tsx`
    - Email/password form fields with inline validation
    - OTP login toggle/section
    - Google and GitHub OAuth buttons
    - Display server error messages inline (no navigation on error)
    - Post-login redirect to originally requested path
    - Install and use react-hook-form for form state management
    - _Requirements: 7.1, 7.7, 7.9_

  - [x] 6.5 Create RegisterPage component
    - Create `mentorman-web/src/auth/RegisterPage.tsx`
    - Email and password fields with inline validation (8–128 chars)
    - Client-side validation before sending to API (password length)
    - Link to login page
    - Display server errors inline (duplicate email 409, validation 422)
    - _Requirements: 7.2, 7.7, 7.8, 7.9_

  - [x] 6.6 Create OTPForm component
    - Create `mentorman-web/src/auth/OTPForm.tsx`
    - Two-step flow: enter email → enter 6-digit code
    - Handle OTP request and verification API calls
    - Display success/error messages inline
    - _Requirements: 7.1_

  - [x] 6.7 Create OAuthCallback component
    - Create `mentorman-web/src/auth/OAuthCallback.tsx`
    - Extract token from URL query parameter on OAuth redirect
    - Store token via AuthProvider login() and redirect to app
    - Handle error parameter (display message, redirect to login)
    - _Requirements: 7.1, 7.3_

  - [x] 6.8 Wire up App.tsx with AuthProvider and routes
    - Wrap app in AuthProvider (replace ClerkProvider)
    - Add routes: /login → LoginPage, /register → RegisterPage, /auth/callback → OAuthCallback
    - Wrap protected routes with ProtectedRoute component
    - Configure api-client with token getters from AuthProvider
    - _Requirements: 7.3, 7.4_

- [x] 7. Checkpoint - Frontend auth integration verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Remove Clerk dependencies
  - [x] 8.1 Remove Clerk from backend
    - Delete `verify_clerk_jwt()` function and `_jwk_client()` from security.py
    - Remove CLERK_ISSUER, CLERK_JWKS_URL from Settings
    - Remove PyJWKClient usage (keep pyjwt[crypto] for HS256)
    - Remove any Clerk-specific environment variables from .env templates
    - _Requirements: 8.1, 8.2_

  - [x] 8.2 Remove Clerk from frontend
    - Uninstall `@clerk/clerk-react` from package.json
    - Delete all ClerkProvider, SignedIn, SignedOut, RedirectToSignIn, SignIn, SignUp imports
    - Remove window.Clerk usage from any source files
    - Remove VITE_CLERK_PUBLISHABLE_KEY from env files
    - Remove HTML preconnect/dns-prefetch links to clerk.accounts.dev
    - _Requirements: 8.3, 8.4, 8.5_

  - [x] 8.3 Verify complete Clerk removal
    - Run case-insensitive search for "clerk" across all source, config, and env template files
    - Confirm zero matches (excluding git history and lock files)
    - _Requirements: 8.6_

- [x] 9. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python (FastAPI + MongoDB), frontend uses TypeScript (React 19)
- The LEGACY_AUTH_ENABLED flag ensures zero-downtime migration for existing integrations

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.6", "2.10"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.7", "2.8", "2.11"] },
    { "id": 4, "tasks": ["2.9", "4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.9", "4.10", "4.12", "4.13"] },
    { "id": 6, "tasks": ["4.6", "4.7", "4.8", "4.11", "4.14"] },
    { "id": 7, "tasks": ["6.1"] },
    { "id": 8, "tasks": ["6.2", "6.3"] },
    { "id": 9, "tasks": ["6.4", "6.5", "6.6", "6.7"] },
    { "id": 10, "tasks": ["6.8"] },
    { "id": 11, "tasks": ["8.1", "8.2"] },
    { "id": 12, "tasks": ["8.3"] }
  ]
}
```
