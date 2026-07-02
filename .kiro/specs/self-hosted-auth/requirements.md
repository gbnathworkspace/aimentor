# Requirements Document

## Introduction

Replace the third-party Clerk authentication provider with a fully self-hosted authentication system for the MentorMan AI Mentor application. The current Clerk integration suffers from production issues (Cloudflare DNS/Worker proxy misconfiguration causing 403s and 525s) and is over-engineered for a small app. The new system must support email+password login, passwordless OTP login, OAuth (Google/GitHub), JWT-based sessions, and user management — all self-hosted on the existing FastAPI + MongoDB stack with a React 19 frontend.

## Glossary

- **Auth_Service**: The backend authentication module in FastAPI that handles user registration, login, token issuance, and token verification
- **Token_Manager**: The component responsible for issuing, refreshing, and revoking JWT access and refresh tokens
- **OTP_Service**: The component responsible for generating, storing, and verifying one-time passwords sent via email
- **OAuth_Handler**: The component that manages the OAuth 2.0 authorization code flow with external identity providers (Google, GitHub)
- **User_Store**: The MongoDB collection and data access layer that persists user accounts, credentials, and profiles
- **Auth_UI**: The React frontend components for login, registration, and account management screens
- **API_Client**: The frontend HTTP client module that attaches authentication tokens to API requests
- **Access_Token**: A short-lived JWT issued by the Auth_Service to authenticate API requests
- **Refresh_Token**: A long-lived opaque token stored in an HTTP-only cookie, used to obtain new Access_Tokens without re-authentication
- **Password_Hasher**: The component that hashes and verifies passwords using bcrypt

## Requirements

### Requirement 1: User Registration with Email and Password

**User Story:** As a new user, I want to create an account with my email and password, so that I can access MentorMan.

#### Acceptance Criteria

1. WHEN a registration request is received with a valid email and password, THE Auth_Service SHALL create a new user record in the User_Store and return an Access_Token in the response body and a Refresh_Token in an HTTP-only cookie
2. WHEN a registration request is received with an email that already exists in the User_Store, THE Auth_Service SHALL reject the request with a 409 Conflict status and a descriptive error message
3. WHEN a registration request is received with a password shorter than 8 characters or longer than 128 characters, THE Auth_Service SHALL reject the request with a 422 status and a validation error message indicating the password length constraint
4. THE Password_Hasher SHALL hash all passwords using bcrypt with a work factor of 12 before storing them in the User_Store
5. WHEN a registration request is received with an email address that does not pass RFC 5322 format validation, THE Auth_Service SHALL reject the request with a 422 status and a validation error message
6. THE Auth_Service SHALL store the user record with fields: email, hashed_password, created_at, auth_method ("email"), is_active (true), is_admin (false), and a generated unique user_id
7. WHEN a registration request is received with a missing or empty email or password field, THE Auth_Service SHALL reject the request with a 422 status and a validation error indicating the missing field

### Requirement 2: Email and Password Login

**User Story:** As a registered user, I want to log in with my email and password, so that I can access my MentorMan sessions.

#### Acceptance Criteria

1. WHEN a login request is received with an email that exists in the User_Store and the correct password, THE Auth_Service SHALL return an Access_Token in the response body and a Refresh_Token in an HTTP-only cookie
2. WHEN a login request is received with an email that exists in the User_Store and an incorrect password, THE Auth_Service SHALL reject the request with a 401 Unauthorized status
3. WHEN a login request is received with an email that does not exist in the User_Store, THE Auth_Service SHALL reject the request with a 401 Unauthorized status
4. THE Auth_Service SHALL use the same error response body for incorrect password and non-existent email to prevent user enumeration
5. WHEN a login request is received with a missing or empty email or password field, THE Auth_Service SHALL reject the request with a 422 status and a validation error message indicating the missing field
6. IF 5 consecutive failed login attempts occur for the same email within 15 minutes, THEN THE Auth_Service SHALL reject further login attempts for that email for 15 minutes and return a 429 Too Many Requests status

### Requirement 3: Passwordless OTP Login

**User Story:** As a user, I want to log in using a one-time password sent to my email, so that I can access MentorMan without remembering a password.

#### Acceptance Criteria

1. WHEN an OTP request is received with an email address that passes RFC 5322 format validation, THE OTP_Service SHALL generate a 6-digit numeric code, store it in the User_Store with a 10-minute expiration timestamp, and send it to the provided email address, invalidating any previously issued unexpired code for that email
2. WHEN an OTP verification request is received with a valid email and correct unexpired code, THE Auth_Service SHALL return an Access_Token in the response body and a Refresh_Token in an HTTP-only cookie
3. WHEN an OTP verification request is received with an expired code, THE Auth_Service SHALL reject the request with a 401 status and an error indicating the code has expired
4. WHEN an OTP verification request is received with an incorrect code, THE Auth_Service SHALL reject the request with a 401 status and an error indicating the code is invalid
5. WHEN an OTP is successfully verified, THE OTP_Service SHALL invalidate the code so it cannot be reused
6. IF 5 failed OTP verification attempts occur for the same email within 15 minutes, THEN THE OTP_Service SHALL reject further verification attempts for that email for 15 minutes with a 429 status and an error indicating the account is temporarily locked
7. WHEN an OTP request is received for an email not yet registered, THE Auth_Service SHALL create a new user record and proceed with OTP delivery
8. IF an OTP request is received with an email address that does not pass RFC 5322 format validation, THEN THE OTP_Service SHALL reject the request with a 400 status and an error indicating the email format is invalid
9. IF more than 5 OTP generation requests are received for the same email within 15 minutes, THEN THE OTP_Service SHALL reject further generation requests for that email for 15 minutes with a 429 status and an error indicating too many requests

### Requirement 4: OAuth Login (Google, GitHub)

**User Story:** As a user, I want to log in using my Google or GitHub account, so that I can access MentorMan without creating a separate password.

#### Acceptance Criteria

1. WHEN an OAuth login is initiated, THE OAuth_Handler SHALL redirect the user to the selected provider's authorization endpoint with the configured client_id, redirect_uri, scope parameters, and a cryptographically random state parameter for CSRF protection
2. WHEN the OAuth provider redirects back with a valid authorization code, THE OAuth_Handler SHALL validate the returned state parameter against the stored value, exchange the code for provider tokens within 10 seconds, extract the user's email and display name, and return an Access_Token and Refresh_Token
3. WHEN the OAuth callback contains an email that already exists in the User_Store, THE OAuth_Handler SHALL link the OAuth identity to the existing user account and issue tokens for that user
4. WHEN the OAuth callback contains an email not found in the User_Store, THE OAuth_Handler SHALL create a new user record with the provider name, provider user ID, email, and display name, and issue tokens
5. IF the OAuth provider returns an error, the authorization code exchange fails, or the state parameter does not match the stored value, THEN THE OAuth_Handler SHALL redirect the user to the login page with an error parameter indicating the failure reason
6. THE OAuth_Handler SHALL store the provider name and provider user ID in the user record for future logins
7. IF the OAuth provider does not return an email address in the user profile response, THEN THE OAuth_Handler SHALL redirect the user to the login page with an error parameter indicating that an email address is required

### Requirement 5: JWT Session Management

**User Story:** As an authenticated user, I want my session to persist without frequent re-logins, so that I have a smooth experience using MentorMan.

#### Acceptance Criteria

1. THE Token_Manager SHALL issue Access_Tokens as JWTs containing the user_id (sub), issued_at (iat), and expiration (exp) claims, signed with HS256 using a server-side secret
2. THE Token_Manager SHALL set Access_Token expiration to 15 minutes
3. THE Token_Manager SHALL issue Refresh_Tokens as opaque random strings of at least 32 bytes of cryptographic randomness with a 7-day expiration, stored in the User_Store
4. WHEN a request is received with a valid Access_Token in the Authorization header using the Bearer scheme, THE Auth_Service SHALL extract the user_id from the token's sub claim and authorize the request, where valid means the token signature verifies against the server-side secret, the exp claim is not in the past, and the sub claim is present
5. WHEN a request is received with an expired or invalid Access_Token, THE Auth_Service SHALL reject the request with a 401 Unauthorized status
6. IF a request is received with no Authorization header or an empty Authorization header, THEN THE Auth_Service SHALL reject the request with a 401 Unauthorized status
7. WHEN a token refresh request is received with a valid unexpired Refresh_Token, THE Token_Manager SHALL issue a new Access_Token and a new Refresh_Token, invalidate the old Refresh_Token in the User_Store, and return both tokens to the client within 2 seconds
8. WHEN a token refresh request is received with an expired or invalid Refresh_Token, THE Token_Manager SHALL reject the request with a 401 status
9. IF a token refresh request is received with a Refresh_Token that was previously invalidated due to rotation, THEN THE Token_Manager SHALL reject the request with a 401 status and invalidate all Refresh_Tokens for that user in the User_Store
10. WHEN a logout request is received, THE Token_Manager SHALL invalidate the user's Refresh_Token in the User_Store and return a success confirmation to the client

### Requirement 6: Legacy Auth Backward Compatibility

**User Story:** As a system operator, I want the legacy API-key authentication to continue working during migration, so that existing integrations are not broken.

#### Acceptance Criteria

1. WHILE the LEGACY_AUTH_ENABLED configuration flag is set to true, THE Auth_Service SHALL accept requests authenticated with a valid X-Api-Key header matching the configured MENTORMAN_API_KEY and a non-empty X-User-Id header, and SHALL use the X-User-Id value as the authenticated user identity
2. WHEN both a Bearer token in the Authorization header and legacy headers (X-Api-Key and X-User-Id) are present on a request, THE Auth_Service SHALL authenticate using the Bearer token and SHALL ignore the legacy headers regardless of their validity
3. IF both a Bearer token and legacy headers are present and the Bearer token is invalid, THEN THE Auth_Service SHALL return a 401 status without falling back to legacy header authentication
4. WHEN LEGACY_AUTH_ENABLED is set to false, THE Auth_Service SHALL reject requests that provide only X-Api-Key and X-User-Id headers without a Bearer token, returning a 401 status with an error message indicating that legacy authentication is disabled
5. IF the LEGACY_AUTH_ENABLED configuration flag is not set, THEN THE Auth_Service SHALL default to true to preserve backward compatibility

### Requirement 7: Frontend Authentication UI

**User Story:** As a user, I want a login and registration interface, so that I can authenticate with MentorMan without Clerk.

#### Acceptance Criteria

1. THE Auth_UI SHALL provide a login page with email/password fields, an OTP login option, and OAuth provider buttons (Google, GitHub)
2. THE Auth_UI SHALL provide a registration page with email and password fields and a link to the login page
3. WHEN a user submits valid credentials on the login page, THE Auth_UI SHALL store the received Access_Token in memory (not in localStorage or sessionStorage) and redirect the user to the main application route
4. WHEN a user is not authenticated and navigates to a protected route, THE Auth_UI SHALL redirect the user to the login page and preserve the originally requested path for post-login redirect
5. IF an API request receives a 401 response indicating an expired Access_Token, THEN THE API_Client SHALL attempt exactly one token refresh using the Refresh_Token and retry the original request before failing
6. IF the token refresh attempt fails or returns a 401 status, THEN THE API_Client SHALL clear the stored Access_Token from memory and redirect the user to the login page
7. THE Auth_UI SHALL display inline validation errors on form submission for invalid email format and password length violations (minimum 8 characters, maximum 128 characters)
8. WHEN a user submits the registration form with a password shorter than 8 characters or longer than 128 characters, THE Auth_UI SHALL display a validation error without sending a request to the Auth_Service
9. IF the Auth_Service returns an error response to a login or registration submission, THEN THE Auth_UI SHALL display the error as a message on the form without navigating away from the page

### Requirement 8: Clerk Removal

**User Story:** As a developer, I want all Clerk dependencies and configuration removed, so that the codebase has no dead third-party auth code.

#### Acceptance Criteria

1. THE Auth_Service SHALL NOT import or reference any Clerk libraries (PyJWT Clerk JWKS verification via PyJWKClient, Clerk SDK) in application code or configuration modules
2. THE Auth_Service SHALL NOT define or read the CLERK_ISSUER, CLERK_JWKS_URL, or any Clerk-prefixed environment variables in its settings
3. THE Frontend SHALL NOT list @clerk/clerk-react or any @clerk-scoped package in its package.json dependencies or devDependencies
4. THE Frontend SHALL NOT import or reference @clerk/clerk-react, ClerkProvider, useClerk, window.Clerk, or Clerk session token retrieval in any source file
5. THE Frontend SHALL NOT include HTML preconnect or dns-prefetch links to clerk.accounts.dev domains
6. IF a text search for the pattern "clerk" (case-insensitive) is run against all application source files, configuration files, and environment templates, THEN the search SHALL return zero matches excluding only the version control history and lock files

### Requirement 9: User Management

**User Story:** As an admin, I want to view and manage user accounts, so that I can support users and maintain the system.

#### Acceptance Criteria

1. WHEN an admin requests the user list at GET /api/admin/users, THE Auth_Service SHALL return a paginated list of user records including user_id, email, auth_method, is_active, is_admin, and created_at, with a default page size of 20 and a maximum page size of 100
2. WHEN an admin requests to deactivate a user account at POST /api/admin/users/{user_id}/deactivate, THE Auth_Service SHALL mark the user as inactive and invalidate all their active Refresh_Tokens
3. WHILE a user account is marked as inactive, THE Auth_Service SHALL reject authentication attempts for that user with a 403 Forbidden status and a descriptive message indicating the account is deactivated
4. THE Auth_Service SHALL identify admin users via an is_admin flag on the user record in the User_Store
5. WHEN a non-admin user attempts to access any endpoint under /api/admin/*, THE Auth_Service SHALL reject the request with a 403 Forbidden status
6. WHEN an admin requests to reactivate a user account at POST /api/admin/users/{user_id}/activate, THE Auth_Service SHALL mark the user as active, allowing future authentication attempts
