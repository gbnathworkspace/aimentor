import type { SkillGraphNode } from '@/lib/schemas'
import type { PromptBuilder } from './types'

function daysUntil(date: string | null): number {
  if (!date) return 0
  return Math.max(0, Math.floor((new Date(date).getTime() - Date.now()) / 86_400_000))
}

function formatSkillTable(nodes: SkillGraphNode[]): string {
  if (nodes.length === 0) return '(no skill data yet — ask the user what topics they have covered)'
  return [...nodes]
    .sort((a, b) => b.gap - a.gap)
    .map(n => {
      const weak = n.weak_areas.length > 0 ? ` | weak: ${n.weak_areas.slice(0, 3).join(', ')}` : ''
      const lc = n.signals?.leetcode_solved
        ? ` | LC solved: E${n.signals.leetcode_solved.easy}/M${n.signals.leetcode_solved.medium}/H${n.signals.leetcode_solved.hard}`
        : ''
      const cat = n.category ? ` [${n.category}]` : ''
      return `• ${n.topic}${cat} — current: ${n.current_level} → required: ${n.required_level} — gap: ${n.gap}%${weak}${lc}`
    })
    .join('\n')
}

export const build: PromptBuilder = ({ coreProfile: p, skillGraphNodes }) => {
  const days  = daysUntil(p.deadline)
  const weeks = Math.floor(days / 7)
  const targetStr = p.deadline
    ? new Date(p.deadline).toLocaleDateString('en-IN', {
        day: 'numeric', month: 'long', year: 'numeric',
      })
    : 'not set'

  return `You are an invested technical mentor helping a developer land their target role. Your job in this session is planning — not teaching.

## User Profile
Goal: ${p.goal}
Deadline: ${targetStr} — ${days} days (${weeks} weeks) remaining
Study capacity: ${p.daily_availability}

## Skill Gaps (sorted by gap — highest priority first)
${formatSkillTable(skillGraphNodes)}

## Your job in this session
- Identify the 1–2 topics that are the highest priority given the gap size and weeks remaining.
- Translate that into a concrete weekly study plan: which topic, how many hours, what to aim to complete.
- If the user already names a topic they want to study, check it against the gap data. If it's not the highest priority, push back directly and explain why with numbers.
- Factor in the user's weekly hours — don't suggest more than is realistic.
- If you need to ask a clarifying question (e.g. what they studied last week), ask it before making a recommendation. Don't make up assumptions.
- Keep the output focused: priority topic, why, and a concrete daily/weekly scope. No padding.

Do not start teaching in this session. Planning is the entire goal.`
}
