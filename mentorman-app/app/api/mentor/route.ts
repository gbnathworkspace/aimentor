import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';
import { requireUserId } from '@/lib/auth';
import { CoreProfileRepo } from '@/lib/db/repositories/core-profile.repo';
import { SkillGraphRepo } from '@/lib/db/repositories/skill-graph.repo';
import { promptStore } from '@/lib/prompts/store';
import { assembleImmediateContext, assembleContext, countTokens } from '@/lib/context-assembler';
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

    // Assemble context with graceful degradation for skipped/missing profiles
    const contextResult = assembleContext({
      coreProfile,
      skillGraphNodes,
      episodes: [],
      conversationWindow: messages ?? [],
      currentTopic: topic,
    });

    const systemPrompt = promptStore.get(sessionMode)(contextResult.promptInput)
      + (contextResult.addendum ?? '');

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

    // Append suggestion chip instructions (skip for evaluation mode — graded answers shouldn't have hints)
    if (sessionMode !== 'evaluation') {
      fullSystemPrompt += `\n\nAfter EVERY message you send, append a suggestions block — quick-reply chips for the user. Rules for suggestions:
- 2–4 options max. Each option must be under 8 words.
- Make chips contextual to what you just discussed or asked.
- If the conversation is open-ended and no clear follow-ups exist, emit an empty array.
- The suggestions block must always appear as the very last thing in your message, in this exact format:
\`\`\`json suggestions
["option 1", "option 2"]
\`\`\``
    }

    const response = await client.messages.create({
      model:      'claude-sonnet-4-6',
      max_tokens: 1024,
      system:     fullSystemPrompt,
      messages:   messages ?? [],
    });

    const raw = response.content[0].type === 'text' ? response.content[0].text : '';

    // Parse and strip suggestions block from the response (same pattern as onboarding)
    let text = raw;
    let suggestions: string[] = [];
    const sugIdx = raw.indexOf('```json suggestions');
    if (sugIdx !== -1) {
      const start = sugIdx + '```json suggestions'.length;
      const end = raw.indexOf('```', start);
      if (end !== -1) {
        try {
          suggestions = JSON.parse(raw.slice(start, end).trim());
          if (!Array.isArray(suggestions)) suggestions = [];
        } catch { suggestions = []; }
        text = (raw.slice(0, sugIdx) + raw.slice(end + 3)).trim();
      }
    }

    return NextResponse.json({ text, suggestions });
  } catch (err) {
    console.error('Mentor route error:', err);
    return NextResponse.json({ text: '' }, { status: 500 });
  }
}
