import { NextRequest, NextResponse } from 'next/server';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { requireUserId } from '@/lib/auth';

export async function POST(req: NextRequest) {
  try {
    const uid = await requireUserId();
    const { goal, deadline, overall_level, daily_availability } = await req.json();

    await CoreProfileRepo.upsert({
      userId: uid,
      goal,
      deadline,
      overall_level: overall_level ?? 'beginner',
      daily_availability: daily_availability ?? '2 hrs/day',
      email: '',
    });

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error('onboarding/complete error:', err);
    return NextResponse.json(
      { ok: false, error: 'Failed to save profile' },
      { status: 500 }
    );
  }
}
