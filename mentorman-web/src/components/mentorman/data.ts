// MentorMan — data, types, constants

export type MessageItem = {
  who: 'mentor' | 'user' | 'verdict' | 'system';
  text: string;
  label?: string;
  nudge?: string;
  code?: string;
  tone?: 'strong' | 'partial' | 'weak';
  _id?: string;
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

export type ModeId = 'planning' | 'topic' | 'doubt' | 'evaluation';
export type DensityId = 'compact' | 'cozy' | 'comfy';

export const MODES: { id: ModeId; label: string; blurb: string }[] = [
  { id: 'planning',   label: 'Planning',   blurb: 'Map the roadmap to your goal — milestones, sequencing, pace.' },
  { id: 'topic',      label: 'Topic',      blurb: 'Deep-dive one subject. Warmups, variants, escalating difficulty.' },
  { id: 'doubt',      label: 'Doubt',      blurb: 'Bring a specific problem. Quick unblock, no long detours.' },
  { id: 'evaluation', label: 'Evaluation', blurb: 'Get tested. Q → graded verdict → adjusted difficulty → score.' },
];

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

export const ACCENTS: Record<string, { ink: string }> = {
  '#34d399': { ink: '#04140d' },
  '#5b9bff': { ink: '#04122e' },
  '#a78bfa': { ink: '#180a36' },
  '#fbbf24': { ink: '#2e1f02' },
  '#fb7185': { ink: '#2e0712' },
};

export const catToMode: Record<string, ModeId> = {
  Topic: 'topic', Doubt: 'doubt', Planning: 'planning', Eval: 'evaluation'
};
