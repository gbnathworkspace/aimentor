import { NextRequest, NextResponse } from 'next/server';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { requireUserId } from '@/lib/auth';

/**
 * POST /api/onboarding/complete-deferred
 *
 * Completes deferred onboarding for users who previously skipped.
 * Updates profile_status from "skipped" to "complete" and merges
 * any new profile data collected during the deferred flow.
 *
 * The Skill Graph bootstrapping happens naturally through the first
 * evaluation or chat session after profile completion.
 *
 * Requirements: 5.3, 5.4
 */
export async function POST(req: NextRequest) {
  try {
    const uid = await requireUserId();
    const body = await req.json().catch(() => ({}));
    const { goal, deadline, overall_level, daily_availability } = body;

    // Get existing profile to merge with
    const existingProfile = await CoreProfileRepo.get(uid);

    if (!existingProfile) {
      return NextResponse.json(
        { ok: false, error: 'No profile found. Please complete full onboarding.' },
        { status: 404 }
      );
    }

    // Merge new values with existing, keeping user-provided data
    const updatedFields: Record<string, unknown> = {
      profile_status: 'complete',
    };

    if (goal) updatedFields.goal = goal;
    if (deadline !== undefined) updatedFields.deadline = deadline ?? null;
    if (overall_level) updatedFields.overall_level = overall_level;
    if (daily_availability) updatedFields.daily_availability = daily_availability;

    await CoreProfileRepo.update(uid, updatedFields);

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error('onboarding/complete-deferred error:', err);
    return NextResponse.json(
      { ok: false, error: 'Failed to complete profile setup' },
      { status: 500 }
    );
  }
}
