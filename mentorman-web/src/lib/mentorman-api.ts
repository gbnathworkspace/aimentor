// ─── Shared domain types ──────────────────────────────────────────────────────
// Recreated for the SPA (the original lib/mentorman-api was removed upstream).
// Imported as `import type` only — they describe the shapes the UI reads.
//
// These are runtime DTOs whose exact field set/casing is mixed (the API shim
// exposes both snake_case and camelCase keys). The frozen components are the
// authority on which fields they read, so we keep named fields for the common
// ones and allow any other key via an index signature.

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface LearningContextDetail {
  label?: string | null;
  situations?: string[];
}

export interface StyleNote {
  category: string;
  note: string;
  source_quote?: string;
  session_id?: string;
  added_at?: string;
}

// Proposed by the post-session profiling agent (app/services/profiling_agent.py),
// awaiting accept/dismiss via POST /api/profile/pending-changes/{field}/(accept|dismiss).
export interface PendingProfileChange {
  field: 'style_note' | 'situation';
  proposed_value: Record<string, string>;
  reason: string;
  session_id: string;
  created_at: string;
}

export interface CoreProfile {
  learning_context_detail?: LearningContextDetail | null;
  style_notes: StyleNote[];
  pending_changes: PendingProfileChange[];
  name?: string;
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
