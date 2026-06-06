import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';
import { requireUserId } from '@/lib/auth';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { SkillGraphRepo } from '@/lib/db/repositories/skill-graph.repo';
import { promptStore } from '@/lib/prompts/store';
import type { SessionMode } from '@/lib/schemas';

const client = new Anthropic();

const VALID_MODES = new Set<SessionMode>(['planning', 'topic', 'doubt', 'evaluation']);

export async function POST(req: NextRequest) {
  try {
    const uid = await requireUserId();
    const { topic, mode, messages } = await req.json();

    const sessionMode: SessionMode = VALID_MODES.has(mode) ? mode : 'topic';

    const [coreProfile, skillGraphNodes] = await Promise.all([
      CoreProfileRepo.get(uid),
      SkillGraphRepo.getAllForUser(uid),
    ]);

    if (!coreProfile) {
      return NextResponse.json(
        { text: "I don't have your profile yet — please complete onboarding first." },
        { status: 400 },
      );
    }

    const systemPrompt = promptStore.get(sessionMode)({
      coreProfile,
      skillGraphNodes,
      episodes: [],
      conversationWindow: [],
      currentTopic: topic,
    });

    const response = await client.messages.create({
      model:      'claude-sonnet-4-6',
      max_tokens: 1024,
      system:     systemPrompt,
      messages:   messages ?? [],
    });

    const text = response.content[0].type === 'text' ? response.content[0].text : '';
    return NextResponse.json({ text });
  } catch (err) {
    console.error('Mentor route error:', err);
    return NextResponse.json({ text: '' }, { status: 500 });
  }
}
