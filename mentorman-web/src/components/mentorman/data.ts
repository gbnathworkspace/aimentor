// MentorMan — data, types, constants

export type MessageItem = {
  who: 'mentor' | 'user' | 'verdict' | 'system' | 'summary' | 'session-end';
  text: string;
  label?: string;
  nudge?: string;
  code?: string;
  tone?: 'strong' | 'partial' | 'weak';
  _id?: string;
  // ISO timestamp from the backend — carried through only to place session-end
  // dividers relative to surrounding messages (see insertSessionDividers).
  timestamp?: string;
  // Tool name(s) currently mid-call (a "start" with no matching "end" yet) for
  // an in-flight streaming mentor reply — see TOOL_MARKER parsing in chat.tsx.
  // Always empty/undefined once the turn settles.
  activeTools?: string[];
  // Full ordered history of tool calls made so far for this in-flight
  // streaming reply (see TOOL_MARKER parsing in chat.tsx) — feeds the
  // "working on this reply" timeline in TopicContextPanel. Cleared once the
  // turn settles, same lifecycle as activeTools.
  toolEvents?: ToolEvent[];
  suggestions?: { title: string; description: string }[];
  attachments?: { name: string; size: number }[];
  summaryBlock?: {
    type: 'summary';
    id: string;
    summary: string;
    compactedRange: { from: string | Date; to: string | Date };
    messageCount: number;
    tokenCount: number;
  };
};

export type ToolEvent = {
  name: string;
  startedAt: number;
  // Set once the matching "end" marker arrives; still undefined means
  // "running" (elapsed time keeps ticking against startedAt).
  endedAt?: number;
};

// This mentor's voice is direct/no-fluff — keep these short and in-character.
// Shared between chat.tsx (inline "thinking" indicator) and
// TopicContextPanel.tsx (the working-on-this-reply timeline).
export const TOOL_LABELS: Record<string, string> = {
  get_user_profile: 'Checking your profile',
  get_skill_state: 'Checking your progress',
  get_past_sessions: 'Recalling past sessions',
  search_documents: 'Searching your documents',
  search_other_topics: 'Searching other topics',
};

// One-line "what this tool call is for" — only used by the timeline, where
// there's room for a bit more than the inline indicator's short label.
export const TOOL_DETAILS: Record<string, string> = {
  get_user_profile: 'Reading your saved profile facts',
  get_skill_state: 'Reading your skill graph for this topic',
  get_past_sessions: 'Reviewing earlier sessions in this topic',
  search_documents: "Searching this topic's attached documents",
  search_other_topics: 'Searching your other topics for relevant context',
};

export type Session = {
  id: string;
  title: string;
  cat: string;
  date: string;
  live?: boolean;
};

export type Topic = {
  name: string;
  cat: string;
  cur: number;
  req: number;
  last: string;
  gap: number;
  level: string;
  levelUp?: { from: string; to: string; up: boolean } | null;  // since-last-session delta (issue #16)
  strong: string[];
  weak: string[];
};

export type DensityId = 'compact' | 'cozy' | 'comfy';

// Single source of truth for mentor voice. Behavioral text lives backend-side
// (prompt_store._TONE_INSTRUCTIONS); the UI only needs ids + labels for the picker.
// Keep ids in sync with backend ToneId (models/chat.py).
export const TONES = [
  { id: 'tough',       label: 'Tough',       blurb: 'Blunt and demanding. Gaps named directly.' },
  { id: 'balanced',    label: 'Balanced',    blurb: 'Supportive but honest. The default.' },
  { id: 'encouraging', label: 'Encouraging', blurb: 'Warm. Frames gaps as progress.' },
] as const;
export type ToneId = typeof TONES[number]['id'];
export const DEFAULT_TONE: ToneId = 'balanced';
