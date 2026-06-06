import { NextRequest, NextResponse } from 'next/server';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { requireUserId } from '@/lib/auth';

export async function GET() {
  const uid = await requireUserId();
  const data = await CoreProfileRepo.get(uid);
  if (!data) return NextResponse.json(null, { status: 404 });
  return NextResponse.json(data);
}

export async function PUT(req: NextRequest) {
  const uid = await requireUserId();
  const body = await req.json();
  const updated = await CoreProfileRepo.update(uid, body);
  return NextResponse.json({ ok: !!updated });
}

export async function DELETE() {
  const uid = await requireUserId();
  await CoreProfileRepo.delete(uid);
  return NextResponse.json({ ok: true });
}
