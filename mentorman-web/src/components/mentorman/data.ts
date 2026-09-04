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
