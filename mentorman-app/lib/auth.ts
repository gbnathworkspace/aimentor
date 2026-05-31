import { auth, currentUser } from '@clerk/nextjs/server'

// ─── Server-side auth helpers ─────────────────────────────────────────────────
// Used by API route handlers to get the current user.
// All routes are already protected by middleware.ts — these helpers exist so
// route handlers can get the userId / user object without repeating boilerplate.

/**
 * Returns the userId from the current Clerk session.
 * Throws if called outside a protected route (shouldn't happen — middleware
 * redirects unauthenticated requests before the route handler runs).
 */
export async function requireUserId(): Promise<string> {
  const { userId } = await auth()
  if (!userId) {
    throw new Error('Unauthorized — no userId in session')
  }
  return userId
}

/**
 * Returns the full Clerk User object for the current session.
 * Useful when you need the user's name / email for prompt injection.
 */
export async function requireUser() {
  const user = await currentUser()
  if (!user) {
    throw new Error('Unauthorized — no user in session')
  }
  return user
}

/**
 * Returns a display name for prompt injection:
 * prefers firstName, falls back to email prefix, then 'there'.
 * Usage: `Hello {{user_name}}` in prompt templates.
 */
export async function getUserDisplayName(): Promise<string> {
  const user = await currentUser()
  if (!user) return 'there'
  if (user.firstName) return user.firstName
  const email = user.emailAddresses[0]?.emailAddress
  return email ? email.split('@')[0] : 'there'
}
