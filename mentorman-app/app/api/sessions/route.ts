import { NextRequest, NextResponse } from 'next/server';
import { SessionRepo } from '@/lib/db/repositories/session.repo';
import { requireUserId } from '@/lib/auth';
import type { SessionMode } from '@/lib/schemas';
import { randomUUID } from 'crypto';

const TYPE_TO_MODE: Record<string, SessionMode> = {
  Topic:      'topic',
  Planning:   'planning',
  Doubt:      'doubt',
  Evaluation: 'evaluation',
  learning:   'topic',
  evaluation: 'evaluation',
};

export async function GET(req: NextRequest) {
  const uid = await requireUserId();
  const { searchParams } = new URL(req.url);
  const limit = Number(searchParams.get('limit') ?? '50');

  const sessions = await SessionRepo.listForUser(uid, limit);

  // Map to the shape the Sidebar's apiSessionToSession expects
  const mapped = sessions.map(s => ({
    session_id:     s.sessionId,
    title:          s.title,
    type:           s.mode,
    topic:          s.topic ?? '',
    topic_category: s.tags[0] ?? '',
    date:           s.createdAt,
    summary:        s.summary ?? '',
  }));

  return NextResponse.json(mapped);
}

export async function POST(req: NextRequest) {
  const uid = await requireUserId();
  const body = await req.json();

  const mode: SessionMode = TYPE_TO_MODE[body.type] ?? 'topic';
  const now = new Date().toISOString();

  const sessionId = randomUUID();

  await SessionRepo.create({
    sessionId,
    userId:    uid,
    title:     body.title ?? 'Untitled session',
    mode,
    topic:     body.topic ?? undefined,
    status:    'active',
    messages:  [],
    tags:      body.topic_category ? [body.topic_category] : [],
    createdAt: now,
    updatedAt: now,
  });

  return NextResponse.json({ sessionId }, { status: 201 });
}
