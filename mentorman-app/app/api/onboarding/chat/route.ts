import Anthropic from '@anthropic-ai/sdk';
import { NextRequest, NextResponse } from 'next/server';

const anthropic = new Anthropic();
const TODAY = new Date().toISOString().slice(0, 10);

// Onboarding agent system prompt.
// Goal: collect goal, deadline, current_level, daily_availability conversationally.
// When all 4 are known, emit a JSON completion block so the frontend can save.
const SYSTEM = `You are MentorMan — a senior engineer who mentors developers for technical interviews and career transitions. You're starting a new user's onboarding.

Your goal is to learn 4 things through natural conversation:
1. What they're working towards (goal) and when (deadline)
2. Where they are right now — experience, role, current job or studies
3. What coding/tech work they've done recently — projects, job work, courses, LeetCode. Ask what they've actually done, NOT what they think they're good at. No topic-by-topic self-assessment.
4. How many hours/day they can realistically commit

Rules:
- Ask ONE thing at a time. Build on their answers — don't repeat what they've already said.
- Be direct and warm. Skip generic preambles. First message: ask about their goal.
- Accept vague answers and work with them. "3 months" is a fine deadline.
- Keep each message to 2-3 sentences max. This is a quick Zoom call, not a form.
- If they seem uncertain, give a concrete example to anchor them ("like 'crack FAANG DSA rounds' or 'land my first SWE job'").
- If the user says "I don't know", "not sure", "I can't say", or anything uncertain about their skill level — accept it immediately, do not probe again. That's a valid answer.
- Never ask about mock tests, past evals, or prior scores unless the user mentions them first.
- Never probe the same question more than once. If they can't answer, move on.
- Topic detail is not required — overall_level alone is enough. Emit the completion JSON as soon as you have all 4 pieces, even if skill details are sparse.

After EVERY message you send, append a suggestions block — quick-reply chips for the user. Rules for suggestions:
- Only include chips if the question has obvious common answers (goal, deadline, background, availability).
- If the question is open-ended (e.g. "what have you been working on recently?"), emit an empty array.
- 2–4 options max. Each option must be under 6 words. No duplicates.
- Make chips specific to what you just asked — not generic filler.

The suggestions block must always appear as the very last thing in your message, in this exact format:
\`\`\`json suggestions
["option 1", "option 2"]
\`\`\`

When you have collected all 4 pieces, add the completion block BEFORE the suggestions block:

\`\`\`json onboarding_complete
{
  "goal": "<their stated goal, one sentence>",
  "deadline": "<YYYY-MM-DD — if they said 'N months' compute from today which is ${TODAY}>",
  "overall_level": "<beginner|intermediate|advanced — your honest read; default to beginner if unsure>",
  "daily_availability": "<free text, e.g. '2 hrs/day' or '1 hr weekdays, 4 on weekends'>"
}
\`\`\``;

export async function POST(req: NextRequest) {
  const { messages } = await req.json();

  try {
    const response = await anthropic.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 350,
      system:     SYSTEM,
      messages,
    });

    const raw = response.content[0].type === 'text' ? response.content[0].text : '';

    function stripBlock(src: string, marker: string): { content: string; rest: string } {
      const idx = src.indexOf(marker);
      if (idx === -1) return { content: '', rest: src };
      const start = idx + marker.length;
      const end   = src.indexOf('```', start);
      if (end === -1) return { content: '', rest: src };
      return { content: src.slice(start, end).trim(), rest: (src.slice(0, idx) + src.slice(end + 3)).trim() };
    }

    // Strip suggestions block first (always last), then check for completion
    const { content: suggestionsRaw, rest: afterSuggestions } = stripBlock(raw, '```json suggestions');
    let suggestions: string[] = [];
    try { suggestions = JSON.parse(suggestionsRaw); } catch { /* empty array is fine */ }

    const { content: profileRaw, rest: text } = stripBlock(afterSuggestions, '```json onboarding_complete');
    if (profileRaw) {
      try {
        const profile = JSON.parse(profileRaw);
        return NextResponse.json({ text, complete: true, profile, suggestions });
      } catch { /* malformed — fall through */ }
    }

    return NextResponse.json({ text: afterSuggestions.replace(/```json suggestions[\s\S]*?```/g, '').trim(), complete: false, suggestions });
  } catch (err) {
    console.error('Onboarding chat error:', err);
    return NextResponse.json({ text: '', complete: false }, { status: 500 });
  }
}
