import { z } from 'zod'

// ─── Core Profile ─────────────────────────────────────────────────────────────
// Layer 1 memory — always injected into every LLM call.
// Flat shape matching what onboarding collects and what the mentor prompt needs.

export const CoreProfileSchema = z.object({
  userId: z.string(),
  goal: z.string().min(1),
  deadline: z.string(),           // "YYYY-MM-DD"
  overall_level: z.string(),      // "beginner" | "intermediate" | "advanced"
  daily_availability: z.string(), // free text: "2 hrs/day"
  email: z.string().default(''),
})

export type CoreProfile = z.infer<typeof CoreProfileSchema>

export const CoreProfileUpdateSchema = CoreProfileSchema.omit({ userId: true }).partial()
export type CoreProfileUpdate = z.infer<typeof CoreProfileUpdateSchema>
