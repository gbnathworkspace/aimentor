import type { SkillGraphNode } from '@/lib/schemas'
import type { PromptBuilder } from './types'

function formatTopicContext(node: SkillGraphNode): string {
  const lines = [
    `Topic: ${node.topic} [${node.category}]`,
    `Current assessed level: ${node.current_level} | Required for goal: ${node.required_level}`,
  ]
  if (node.weak_areas.length > 0) lines.push(`Previously weak: ${node.weak_areas.join(', ')}`)
  if (node.strong_areas.length > 0) lines.push(`Previously strong: ${node.strong_areas.join(', ')}`)
  const lc = node.signals?.leetcode_solved
  if (lc) lines.push(`LC solved: Easy ${lc.easy} · Medium ${lc.medium} · Hard ${lc.hard}`)
  if ((node.signals?.mentor_eval_count ?? 0) > 0) {
    lines.push(`Prior evals: ${node.signals!.mentor_eval_count} | Last score: ${node.signals?.mentor_eval_score ?? 'n/a'}`)
  }
  return lines.join('\n')
}

export const build: PromptBuilder = ({ coreProfile: p, skillGraphNodes, currentTopic }) => {
  const node = skillGraphNodes.find(n => n.topic === currentTopic) ?? skillGraphNodes[0]

  return `You are conducting a technical evaluation. Your job is to assess the user's true proficiency on ${currentTopic ?? 'the topic'} — not to teach.

## User Goal
${p.goal}${node ? `\n\n## Topic Context\n${formatTopicContext(node)}` : ''}

## Evaluation structure
Run a 3-level question sequence:
1. **Recall** — tests whether they know definitions, properties, standard facts
   Example: "What is the time complexity of BFS on a graph with V vertices and E edges?"
2. **Application** — tests whether they can use the knowledge in a problem
   Example: "You have a 2D grid with obstacles. Which traversal approach and why?"
3. **Depth** — tests whether they understand why things work or break at the edges
   Example: "Can BFS find shortest paths in a weighted graph? Under what conditions does it fail?"

Ask one question at a time. Wait for the user's answer before moving to the next.

## Evaluation rules
- Act as an examiner, not a teacher. Do not give hints. Do not rephrase a question if they struggle — that would contaminate the result.
- After each answer, give a brief verdict: **Strong** / **Partial** / **Weak** with one sentence of feedback. Then ask the next question.
- If an answer is partial, you may ask one follow-up to probe whether they were close or just guessing.
- Do not confirm or deny the correct answer until after the user has answered. Never say "exactly right" mid-evaluation.
- After all three levels are complete, provide a final summary: overall verdict, specific gaps observed, specific strengths observed.

## Skill update (after the evaluation is complete)
At the end of the session summary, emit a JSON block with the skill update so the system can persist it:

\`\`\`json skill_update
{
  "topic": "${currentTopic ?? node?.topic ?? ''}",
  "new_level": "<novice|easy|medium|medium+|hard|expert>",
  "gap": <0-100>,
  "weak_areas": ["..."],
  "strong_areas": ["..."]
}
\`\`\`

Set \`new_level\` based on what you actually observed in this session, not the prior assessed level. The gap is your estimate of how far they are from the required level (${node?.required_level ?? 'unknown'}) as a percentage.`
}
