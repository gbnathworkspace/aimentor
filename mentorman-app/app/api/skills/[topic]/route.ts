import { NextRequest, NextResponse } from 'next/server';
import { SkillGraphRepo } from '@/lib/db/repositories/skill-graph.repo';
import { requireUserId } from '@/lib/auth';

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ topic: string }> },
) {
  const uid = await requireUserId();
  const { topic } = await params;
  const body = await req.json();
  const updated = await SkillGraphRepo.patch(uid, decodeURIComponent(topic), body);
  return NextResponse.json({ ok: !!updated });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ topic: string }> },
) {
  const uid = await requireUserId();
  const { topic } = await params;
  await SkillGraphRepo.delete(uid, decodeURIComponent(topic));
  return NextResponse.json({ ok: true });
}
