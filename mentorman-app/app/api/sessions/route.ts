import { NextRequest, NextResponse } from 'next/server';
import * as api from '@/lib/mentorman-api';

const userId = () => process.env.DEMO_USER_ID ?? 'demo_user';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const limit = searchParams.get('limit');
  const offset = searchParams.get('offset');
  const topic = searchParams.get('topic');
  const data = await api.listSessions(userId(), {
    limit: limit ? Number(limit) : undefined,
    offset: offset ? Number(offset) : undefined,
    topic: topic ?? undefined,
  });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const ok = await api.saveSession(userId(), body);
  return NextResponse.json({ ok }, { status: ok ? 201 : 500 });
}
