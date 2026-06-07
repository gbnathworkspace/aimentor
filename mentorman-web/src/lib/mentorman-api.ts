// ─── Shared domain types ──────────────────────────────────────────────────────
// Recreated for the SPA (the original lib/mentorman-api was removed upstream).
// Imported as `import type` only — they describe the shapes the UI reads.
//
// These are runtime DTOs whose exact field set/casing is mixed (the API shim
// exposes both snake_case and camelCase keys). The frozen components are the
// authority on which fields they read, so we keep named fields for the common
// ones and allow any other key via an index signature.

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface CoreProfile {
  goal: string;
  deadline: string;
  overall_level: string;
  daily_availability: string;
  email?: string;
  [key: string]: any;
}

export interface SkillNode {
  topic: string;
  current_level: string;
  required_level: string;
  gap: any;
  signals?: Record<string, any>;
  [key: string]: any;
}

export interface SessionRecord {
  title: string;
  [key: string]: any;
}

export type SessionMode = string;
