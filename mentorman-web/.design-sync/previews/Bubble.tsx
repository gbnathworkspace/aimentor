import React from 'react';
import { Bubble } from 'mentorman-web';

// Bubble is the workhorse of the chat surface: it wraps Msg (avatar + who-line),
// runs `item.text` through the inline markdown renderer, and appends a
// read-aloud control on mentor turns. Content below is real mentoring dialogue —
// these cards are browsed by humans and imitated by the design agent.

const chat: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 620 };

/** The canonical pair: a learner question and the mentor's reply. */
export function Conversation() {
  return (
    <div style={chat}>
      <Bubble
        who="user"
        item={{ text: 'I keep mixing up `useMemo` and `useCallback`. When does each actually matter?' }}
      />
      <Bubble
        who="mentor"
        item={{
          text:
            'Both memoize — they differ in **what**.\n\n' +
            '`useMemo` caches a *computed value*. `useCallback` caches a *function identity*.\n\n' +
            'The tell: if you are passing it to a memoized child as a prop, you want `useCallback`. ' +
            'If you are avoiding an expensive recomputation on every render, you want `useMemo`.',
        }}
      />
    </div>
  );
}

/** Mentor turns can carry an eyebrow label naming the teaching move. */
export function WithLabel() {
  return (
    <div style={chat}>
      <Bubble
        who="mentor"
        item={{
          label: 'Checking understanding',
          text: 'Before I go further — what do you expect to happen if the dependency array is left out entirely?',
        }}
      />
    </div>
  );
}

/** A nudge is a secondary hint attached under the main answer. */
export function WithNudge() {
  return (
    <div style={chat}>
      <Bubble
        who="mentor"
        item={{
          text: 'Close. Your reduce works, but it mutates the accumulator, so the original array changes too.',
          nudge: 'Try returning a **new** object from each step instead of assigning onto `acc`.',
        }}
      />
    </div>
  );
}

/**
 * The markdown surface in full: headings, lists, a table, inline code and a
 * fenced block. This is the card to look at when judging typography — it
 * exercises Clash Grotesk for prose and JetBrains Mono for code.
 */
export function RichExplanation() {
  return (
    <div style={chat}>
      <Bubble
        who="mentor"
        item={{
          label: 'Deep dive',
          text:
            '## Indexing strategy\n\n' +
            'You have three read patterns, and only one of them is currently served by an index.\n\n' +
            '| Query | Rows scanned | Index |\n' +
            '|---|---|---|\n' +
            '| by `user_id` | 12 | yes |\n' +
            '| by `created_at` | 480,000 | no |\n' +
            '| by `status` | 480,000 | no |\n\n' +
            '### What to do first\n\n' +
            '1. Add a composite index on `(user_id, created_at)`\n' +
            '2. Re-run the explain plan\n' +
            '3. Only then consider `status`\n\n' +
            'The composite covers both the first and second query:\n\n' +
            '```sql\nCREATE INDEX idx_sessions_user_created\n  ON sessions (user_id, created_at DESC);\n```\n\n' +
            '> Leading column first — an index on `(created_at, user_id)` would not serve the `user_id` lookup.\n\n' +
            'See the [Postgres docs on multicolumn indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) for why the order is not symmetric.',
        }}
      />
    </div>
  );
}

/** A longer learner turn — user bubbles get no avatar image, no speak control. */
export function LearnerDetail() {
  return (
    <div style={chat}>
      <Bubble
        who="user"
        item={{
          text:
            "Here's what I tried:\n\n" +
            '```python\ndef parse(rows):\n    out = {}\n    for r in rows:\n        out[r.id] = r\n    return out\n```\n\n' +
            'It works, but it feels like there should be a one-liner. Is a dict comprehension actually better here, or just shorter?',
        }}
      />
    </div>
  );
}
