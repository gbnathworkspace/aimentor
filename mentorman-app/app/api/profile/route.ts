import { NextRequest, NextResponse } from 'next/server';
import * as api from '@/lib/mentorman-api';

// TODO: replace with Clerk auth() userId once ClerkProvider is configured
const userId = () => process.env.DEMO_USER_ID ?? 'demo_user';

export async function GET() {
  const data = await api.getProfile(userId());
  if (!data) return NextResponse.json(null, { status: 404 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const ok = await api.createProfile({ ...body, user_id: userId() });
  return NextResponse.json({ ok }, { status: ok ? 201 : 500 });
}

export async function PUT(req: NextRequest) {
  const body = await req.json();
  const ok = await api.updateProfile(userId(), body);
  return NextResponse.json({ ok });
}

export async function DELETE() {
  const ok = await api.deleteProfile(userId());
  return NextResponse.json({ ok });
}
