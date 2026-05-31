import { NextRequest, NextResponse } from 'next/server';
import * as api from '@/lib/mentorman-api';

const userId = () => process.env.DEMO_USER_ID ?? 'demo_user';

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ topic: string }> },
) {
  const { topic } = await params;
  const body = await req.json();
  const ok = await api.updateSkill(userId(), decodeURIComponent(topic), body);
  return NextResponse.json({ ok });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ topic: string }> },
) {
  const { topic } = await params;
  const ok = await api.deleteSkill(userId(), decodeURIComponent(topic));
  return NextResponse.json({ ok });
}
