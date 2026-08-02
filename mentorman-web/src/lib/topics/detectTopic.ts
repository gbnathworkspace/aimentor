/**
 * Guess which existing topic a message belongs to, by matching the topic's
 * title and subject words against the text.
 *
 * ponytail: word overlap, not an LLM call — the candidate set is the user's own
 * topic list, so "explain react hooks" hitting the "React" topic needs no model.
 * Swap in a backend/LLM classifier if titles stop being descriptive enough.
 */

import type { TopicListItem } from './types';

/** Words too common to identify a topic — they'd match nearly any message. */
const STOP = new Set([
  'the', 'and', 'for', 'with', 'that', 'this', 'what', 'how', 'why', 'about',
  'from', 'into', 'your', 'you', 'are', 'was', 'can', 'not', 'new',
  'topic', 'chat', 'session', 'help', 'question', 'explain', 'review', 'quiz',
]);

/** Lowercased alphanumeric words of length >= 3, minus stopwords. */
function keywords(s: string): string[] {
  const out: string[] = [];
  for (const w of s.toLowerCase().split(/[^a-z0-9+#]+/)) {
    if (w.length >= 3 && !STOP.has(w)) out.push(w);
  }
  return out;
}

/**
 * Returns the best-matching topic, or null when nothing meaningful overlaps.
 * `topics` is expected in lastActiveAt-desc order — ties go to the more recent
 * topic, which is the one the user is likelier to mean.
 */
export function detectTopic(text: string, topics: TopicListItem[]): TopicListItem | null {
  const words = new Set(keywords(text));
  if (words.size === 0) return null;

  let best: TopicListItem | null = null;
  let bestScore = 0;

  for (const t of topics) {
    const terms = new Set(keywords(`${t.title} ${t.subject || ''}`));
    if (terms.size === 0) continue;
    let hits = 0;
    for (const term of terms) if (words.has(term)) hits++;
    if (hits === 0) continue;
    // Normalise by topic length so a long rambling title can't out-score a
    // short precise one ("React" beats "hello, quick sanity check react-ish").
    const score = hits / terms.size;
    if (score > bestScore) {
      bestScore = score;
      best = t;
    }
  }

  return best;
}
