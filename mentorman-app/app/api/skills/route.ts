import { NextRequest, NextResponse } from 'next/server';
import { SkillGraphRepo } from '@/lib/db/repositories/skill-graph.repo';
import { requireUserId } from '@/lib/auth';

export async function GET() {
  const uid = await requireUserId();
  const nodes = await SkillGraphRepo.getAllForUser(uid);
  return NextResponse.json(nodes);
}

export async function POST(req: NextRequest) {
  try {
    const uid = await requireUserId();
    const body = await req.json();
    const node = await SkillGraphRepo.upsert({
      userId:         uid,
      topic:          body.topic,
      category:       body.category,
      required_level: body.required_level ?? 'medium',
      current_level:  body.current_level  ?? 'easy',
      gap:            typeof body.gap === 'number' ? body.gap : 50,
      signals:        body.signals,
      strong_areas:   body.strong_areas ?? [],
      weak_areas:     body.weak_areas   ?? [],
    });
    return NextResponse.json(node, { status: 201 });
  } catch (err) {
    console.error('POST /api/skills error:', err);
    return NextResponse.json({ error: 'Invalid skill data' }, { status: 400 });
  }
}
