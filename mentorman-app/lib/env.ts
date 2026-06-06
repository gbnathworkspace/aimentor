import { z } from 'zod'

// ─── Environment variable validation ─────────────────────────────────────────
// Runs at module import time — if any required var is missing or empty,
// the server throws immediately (boot time) rather than at the first user request.
// Import this module in instrumentation.ts so it runs on startup.

const EnvSchema = z.object({
  // Database
  MONGODB_URI: z.string().min(1, 'MONGODB_URI is required'),

  // Clerk auth
  CLERK_SECRET_KEY: z.string().min(1, 'CLERK_SECRET_KEY is required'),
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: z.string().min(1, 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is required'),

  // AI providers
  ANTHROPIC_API_KEY: z.string().min(1, 'ANTHROPIC_API_KEY is required'),

  // Optional — warn but don't crash if missing
  VOYAGE_API_KEY:          z.string().optional(),
  AWS_ACCESS_KEY_ID:       z.string().optional(),
  AWS_SECRET_ACCESS_KEY:   z.string().optional(),
  AWS_REGION:              z.string().optional(),
  S3_BUCKET_NAME:          z.string().optional(),
  RETRIEVAL_METHOD:        z.string().optional(),
})

const parsed = EnvSchema.safeParse(process.env)

if (!parsed.success) {
  const missing = parsed.error.issues.map(i => `  • ${i.path[0]}: ${i.message}`)
  throw new Error(
    `\n\n❌ Missing or invalid environment variables:\n${missing.join('\n')}\n\n` +
    `Copy .env.local.example to .env.local and fill in the required values.\n`
  )
}

export const env = parsed.data
