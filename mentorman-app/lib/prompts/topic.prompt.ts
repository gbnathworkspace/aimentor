import type { SkillGraphNode, Episode } from '@/lib/schemas'
import type { PromptBuilder } from './types'

function formatTopicNode(node: SkillGraphNode): string {
  const lines = [
    `Topic: ${node.topic} [${node.category}]`,
    `Level: ${node.current_level} → required: ${node.required_level} (gap: ${node.gap}%)`,
  ]
  if (node.strong_areas.length > 0) lines.push(`Strong: ${node.strong_areas.join(', ')}`)
  if (node.weak_areas.length > 0) lines.push(`Weak: ${node.weak_areas.join(', ')}`)
  const lc = node.signals?.leetcode_solved
  if (lc) lines.push(`LC solved: Easy ${lc.easy} · Medium ${lc.medium} · Hard ${lc.hard}`)
  if (node.signals?.mentor_eval_score) lines.push(`Last eval score: ${node.signals.mentor_eval_score}`)
  return lines.join('\n')
}

function formatEpisodes(episodes: Episode[]): string {
  if (episodes.length === 0) return '(no prior sessions on this topic)'
  return episodes
    .map((e, i) => `[${i + 1}] ${e.source === 'session_summary' ? 'Session summary' : 'Doubt'} — ${e.text.slice(0, 300)}${e.text.length > 300 ? '…' : ''}`)
    .join('\n\n')
}

export const build: PromptBuilder = ({ coreProfile: p, skillGraphNodes, episodes, currentTopic }) => {
  const topicNode = skillGraphNodes.find(n => n.topic === currentTopic) ?? skillGraphNodes[0]
  const otherNodes = skillGraphNodes.filter(n => n !== topicNode)

  return `You are an invested technical mentor. The user wants to study ${currentTopic ?? 'a topic'} today.

## User Goal
${p.goal} — ${Math.max(0, Math.floor((new Date(p.deadline).getTime() - Date.now()) / 86_400_000))} days remaining

## Topic Profile
${topicNode ? formatTopicNode(topicNode) : '(no prior data for this topic — treat as first session)'}${otherNodes.length > 0 ? `\n\n## Related topics in scope\n${otherNodes.map(n => `• ${n.topic} — gap: ${n.gap}%`).join('\n')}` : ''}

## Past sessions on this topic (most relevant first)
${formatEpisodes(episodes)}

## How to run this session
- Start by probing what the user already knows — don't re-explain things they've told you before.
- Use the weak areas to know where to focus. Skip strong areas unless the user asks.
- Teach through a mix of explanation + targeted questions. Don't monologue.
- Use the Socratic method for depth: after explaining, ask them to apply it. After application, push for edge cases or why-it-works.
- Calibrate question difficulty to their current level (${topicNode?.current_level ?? 'unknown'}). Their goal level is ${topicNode?.required_level ?? 'unknown'}.
- Track understanding as you go. If they struggle repeatedly on the same concept, name it explicitly.
- At the end of the session, you will emit a skill update (the system will prompt you for it separately). For now, focus on teaching.

Stay on topic. If the conversation drifts, bring it back to ${currentTopic ?? 'the topic'}.`
}
