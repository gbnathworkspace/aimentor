// ─── Shared domain types ──────────────────────────────────────────────────────
// Re-exported for backward compatibility with components that import from this path.
// The canonical schemas live in lib/schemas/ — this file provides loose DTO types
// that the UI components reference via `import type`.

/* eslint-disable @typescript-eslint/no-explicit-any */

export type { CoreProfile } from './schemas/core-profile.schema';

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
