import { NextRequest, NextResponse } from 'next/server';
import { randomUUID } from 'crypto';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { SessionRepo } from '@/lib/db/repositories/session.repo';
import { requireUserId } from '@/lib/auth';

// ─── Default profile values for skipped onboarding ────────────────────────────
const SKIP_DEFAULTS = {
  goal: 'exploring',
  deadline: null,
  daily_availability: '1 hour',
  overall_level: 'beginner',
} as const;

export async function POST(req: NextRequest) {
  try {
    const uid = await requireUserId();
    const body = await req.json().catch(() => ({}));
    const partial = body.partialProfile ?? {};

    // Merge user-provided partial profile with defaults
    const profileData = {
      userId: uid,
      goal: partial.goal || SKIP_DEFAULTS.goal,
      deadline: partial.deadline ?? SKIP_DEFAULTS.deadline,
      daily_availability: partial.daily_availability || SKIP_DEFAULTS.daily_availability,
      overall_level: partial.overall_level || SKIP_DEFAULTS.overall_level,
      email: '',
      profile_status: 'skipped' as const,
    };

    // Upsert CoreProfile with profile_status: "skipped"
    // Do NOT create any Skill Graph documents
    await CoreProfileRepo.upsert(profileData);

    // Create a new chat session for the user
    const sessionId = randomUUID();
    const now = new Date().toISOString();

    await SessionRepo.create({
      sessionId,
      userId: uid,
      title: 'New session',
      mode: 'topic',
      status: 'active',
      messages: [],
      tags: [],
      createdAt: now,
      updatedAt: now,
    });

    return NextResponse.json({ ok: true, sessionId });
  } catch (err) {
    console.error('onboarding/skip error:', err);
    return NextResponse.json(
      { ok: false, error: 'Failed to skip onboarding' },
      { status: 500 }
    );
  }
}
