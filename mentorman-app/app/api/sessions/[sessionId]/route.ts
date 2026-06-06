import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';
import { requireUserId } from '@/lib/auth';
import { SessionRepo } from '@/lib/db/repositories/session.repo';
import { SkillGraphRepo } from '@/lib/db/repositories/skill-graph.repo';
import { SkillUpdateToolSchema } from '@/lib/schemas';
import type { Message } from '@/lib/schemas';

const client = new Anthropic();

// Extract ```json skill_update { ... } ``` block from last assistant message
function extractSkillUpdate(messages: { role: string; content: string }[]) {
  const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
  if (!lastAssistant) return null;

  const match = lastAssistant.content.match(/```json skill_update\s*([\s\S]*?)```/);
  if (!match) return null;

  try {
    const parsed = SkillUpdateToolSchema.safeParse(JSON.parse(match[1]));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

async function generateSummary(messages: { role: string; content: string }[]): Promise<string> {
  const last10 = messages.slice(-10);
  const formatted = last10
    .map(m => `${m.role === 'assistant' ? 'Mentor' : 'You'}: ${m.content}`)
    .join('\n');

  const res = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 150,
    system:     'Summarize this mentoring session in 2–3 sentences: what was covered, key insight the learner gained, and any skill gaps observed. Be specific — no filler.',
    messages:   [{ role: 'user', content: formatted }],
  });

  return res.content[0].type === 'text' ? res.content[0].text.trim() : '';
}

// PATCH /api/sessions/[sessionId] — SessionSaveHandler
// Called from chat.tsx endSession() with full messages array
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const uid = await requireUserId();
    const { sessionId } = await params;
    const { messages, mode, topic } = await req.json() as {
      messages: { role: string; content: string }[];
      mode:     string;
      topic?:   string;
    };

    // Run summary generation and skill_update extraction in parallel
    const [summary, skillUpdate] = await Promise.all([
      generateSummary(messages),
      Promise.resolve(extractSkillUpdate(messages)),
    ]);

    // Persist skill update to skill graph if evaluation mode emitted one
    if (skillUpdate && topic) {
      await SkillGraphRepo.applyUpdate(uid, {
        topic,
        new_level:    skillUpdate.new_level,
        gap:          skillUpdate.gap,
        weak_areas:   skillUpdate.weak_areas,
        strong_areas: skillUpdate.strong_areas,
      });
    }

    // Convert to Message schema shape and save full session
    const dbMessages: Message[] = messages.map((m, i) => ({
      id:        `msg-${i}`,
      role:      (m.role === 'assistant' ? 'mentor' : 'user') as 'mentor' | 'user',
      content:   m.content,
      timestamp: new Date().toISOString(),
    }));

    await SessionRepo.save(sessionId, dbMessages, summary);

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error('SessionSaveHandler error:', err);
    return NextResponse.json({ ok: false }, { status: 500 });
  }
}
