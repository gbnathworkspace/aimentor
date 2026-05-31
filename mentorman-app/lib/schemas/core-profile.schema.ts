import { z } from 'zod'

// ─── Core Profile ─────────────────────────────────────────────────────────────
// Layer 1 memory — always injected into every LLM call, no retrieval needed.
// Written by: IngestionService (onboarding), SettingsService (user edits).
// Read by: ContextAssembler (every session call).

export const AvailabilitySchema = z.object({
  weekdayHrs: z.number().min(0).max(24),
  weekendHrs: z.number().min(0).max(24),
  totalWeeklyHrs: z.number().min(0), // derived: weekdayHrs*5 + weekendHrs*2
})

export const EducationSchema = z.object({
  degree: z.string(),
  field: z.string(),
  institution: z.string().optional(),
})

export const CoreProfileSchema = z.object({
  userId: z.string(),
  goal: z.string().min(1),               // e.g. "20 LPA SWE role"
  targetDate: z.string().datetime(),     // ISO 8601
  availability: AvailabilitySchema,
  currentRole: z.string().optional(),    // e.g. "SWE II"
  yearsOfExperience: z.number().min(0).optional(),
  education: EducationSchema.optional(),
  skills: z.array(z.string()).default([]),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
})

export type CoreProfile = z.infer<typeof CoreProfileSchema>
export type Availability = z.infer<typeof AvailabilitySchema>

// Partial schema for Settings screen updates — only editable fields
export const CoreProfileUpdateSchema = CoreProfileSchema.pick({
  goal: true,
  targetDate: true,
  availability: true,
}).partial()

export type CoreProfileUpdate = z.infer<typeof CoreProfileUpdateSchema>
