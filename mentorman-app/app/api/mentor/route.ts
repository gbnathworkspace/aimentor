import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';
import { requireUserId } from '@/lib/auth';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { SkillGraphRepo } from '@/lib/db/repositories/skill-graph.repo';
import { promptStore } from '@/lib/prompts/store';
import { assembleImmediateContext, countTokens } from '@/lib/context-assembler';
import type { SessionMode } from '@/lib/schemas';

const client = new Anthropic();

const VALID_MODES = new Set<SessionMode>(['planning', 'topic', 'doubt', 'evaluation']);

export async function POST(req: NextRequest) {
  try {
    const uid = await requireUserId();
    const { topic, mode, messages, sessionId } = await req.json();

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

    // Count tokens for the core context (system prompt with Core Profile + Skill Graph)
    // These tokens are never dropped — they always take priority
    const coreContextTokens = countTokens(systemPrompt)

    // Assemble ImmediateContext with token budget enforcement
    // If combined context exceeds budget, ImmediateContext blocks are dropped oldest-first
    const immediateContext = sessionId
      ? await assembleImmediateContext(sessionId, {
          contextTokenCounts: { coreContextTokens, episodicRagTokens: 0 },
        })
      : null

    // Build the full system prompt with ImmediateContext integration
    // Order: system prompt (Core Profile + Skill Graph) → ImmediateContext → Episodic RAG
    let fullSystemPrompt = systemPrompt

    if (immediateContext && immediateContext.systemInstruction) {
      fullSystemPrompt += `\n\n## Uploaded File Context\n${immediateContext.systemInstruction}`
    }

    if (immediateContext && immediateContext.formattedText) {
      fullSystemPrompt += `\n\n## File Content\n${immediateContext.formattedText}`
    }

    const response = await client.messages.create({
      model:      'claude-sonnet-4-6',
      max_tokens: 1024,
      system:     fullSystemPrompt,
      messages:   messages ?? [],
    });

    const text = response.content[0].type === 'text' ? response.content[0].text : '';
    return NextResponse.json({ text });
  } catch (err) {
    console.error('Mentor route error:', err);
    return NextResponse.json({ text: '' }, { status: 500 });
  }
}
