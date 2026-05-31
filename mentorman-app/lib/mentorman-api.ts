// Server-side client for the MentorMan layered-memory backend.
// All calls require MENTORMAN_API_KEY env var.

const BASE = 'https://mentorman.co.in';

function h(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-API-Key': process.env.MENTORMAN_API_KEY ?? '',
  };
}

// ---------- Types -----------------------------------------------

export type CoreProfile = {
  user_id: string;
  goal: string;
  deadline: string;
  overall_level: string;
  daily_availability: string;
  email: string;
};

export type ProfileUpdate = Partial<Omit<CoreProfile, 'user_id'>>;

export type SkillNode = {
  topic: string;
  required_level: string;
  current_level: string;
  gap: string;
  signals?: Record<string, unknown>;
};

export type SkillUpdate = Partial<Omit<SkillNode, 'topic'>>;

export type SkillUpdateSnapshot = {
  current_level?: string;
  weak_areas?: string[];
  strong_areas?: string[];
};

export type EpisodicEntry = {
  topic: string;
  topic_category: string;
  type: string;
  date: string;
  title: string;
  summary: string;
  skill_update?: SkillUpdateSnapshot | null;
};

export type SessionRecord = EpisodicEntry & { session_id: string };

export type SearchQuery = { query: string; limit?: number; topic?: string };

// ---------- Profile (L1) ----------------------------------------

export async function getProfile(userId: string): Promise<CoreProfile | null> {
  const r = await fetch(`${BASE}/memory/profile/${userId}`, { headers: h() });
  if (!r.ok) return null;
  return r.json();
}

export async function createProfile(profile: CoreProfile): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/profile`, {
    method: 'POST', headers: h(), body: JSON.stringify(profile),
  });
  return r.ok;
}

export async function updateProfile(userId: string, update: ProfileUpdate): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/profile/${userId}`, {
    method: 'PUT', headers: h(), body: JSON.stringify(update),
  });
  return r.ok;
}

export async function deleteProfile(userId: string): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/profile/${userId}`, { method: 'DELETE', headers: h() });
  return r.ok;
}

// ---------- Skill Graph (L2) ------------------------------------

export async function getAllSkills(userId: string): Promise<SkillNode[]> {
  const r = await fetch(`${BASE}/memory/skill/${userId}`, { headers: h() });
  if (!r.ok) return [];
  return r.json();
}

export async function getSkill(userId: string, topic: string): Promise<SkillNode | null> {
  const r = await fetch(`${BASE}/memory/skill/${userId}/${encodeURIComponent(topic)}`, { headers: h() });
  if (!r.ok) return null;
  return r.json();
}

export async function createSkill(userId: string, skill: SkillNode): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/skill/${userId}`, {
    method: 'POST', headers: h(), body: JSON.stringify(skill),
  });
  return r.ok;
}

export async function updateSkill(userId: string, topic: string, update: SkillUpdate): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/skill/${userId}/${encodeURIComponent(topic)}`, {
    method: 'PUT', headers: h(), body: JSON.stringify(update),
  });
  return r.ok;
}

export async function deleteSkill(userId: string, topic: string): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/skill/${userId}/${encodeURIComponent(topic)}`, {
    method: 'DELETE', headers: h(),
  });
  return r.ok;
}

// ---------- Episodic Memory (L3) --------------------------------

export async function listSessions(
  userId: string,
  opts?: { limit?: number; offset?: number; topic?: string },
): Promise<SessionRecord[]> {
  const p = new URLSearchParams();
  if (opts?.limit != null) p.set('limit', String(opts.limit));
  if (opts?.offset != null) p.set('offset', String(opts.offset));
  if (opts?.topic) p.set('topic', opts.topic);
  const r = await fetch(`${BASE}/memory/episodic/${userId}?${p}`, { headers: h() });
  if (!r.ok) return [];
  return r.json();
}

export async function saveSession(userId: string, entry: EpisodicEntry): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/episodic/${userId}`, {
    method: 'POST', headers: h(), body: JSON.stringify(entry),
  });
  return r.ok;
}

export async function searchSessions(userId: string, query: SearchQuery): Promise<SessionRecord[]> {
  const r = await fetch(`${BASE}/memory/episodic/${userId}/search`, {
    method: 'POST', headers: h(), body: JSON.stringify(query),
  });
  if (!r.ok) return [];
  return r.json();
}

export async function deleteSession(userId: string, sessionId: string): Promise<boolean> {
  const r = await fetch(`${BASE}/memory/episodic/${userId}/${sessionId}`, {
    method: 'DELETE', headers: h(),
  });
  return r.ok;
}
