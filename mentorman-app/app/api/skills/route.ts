import { NextRequest, NextResponse } from 'next/server';
import * as api from '@/lib/mentorman-api';

const userId = () => process.env.DEMO_USER_ID ?? 'demo_user';

export async function GET() {
  const data = await api.getAllSkills(userId());
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const ok = await api.createSkill(userId(), body);
  return NextResponse.json({ ok }, { status: ok ? 201 : 500 });
}
