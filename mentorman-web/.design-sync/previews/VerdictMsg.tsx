import React from 'react';
import { VerdictMsg } from 'mentorman-web';

// The mentor's assessment of a learner's answer. `tone` is the variant axis and
// drives the pill: strong (accent), partial (warn), weak (danger). `label` is
// the level the answer demonstrated; `text` runs through the markdown renderer.

const wrap: React.CSSProperties = { maxWidth: 620 };

/** All three tones together — this is the axis that most changes appearance. */
export function Tones() {
  return (
    <div style={{ ...wrap, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <VerdictMsg
        item={{
          tone: 'strong',
          label: 'L3 — Applied',
          text: 'Exactly right, and you named the trade-off without being asked. The write amplification point is the one most people miss.',
        }}
      />
      <VerdictMsg
        item={{
          tone: 'partial',
          label: 'L2 — Recall',
          text: 'The mechanism is right but the conclusion is not. You said the index makes writes slower — true — then concluded it should be dropped. Dropping it makes the reads slower instead.',
        }}
      />
      <VerdictMsg
        item={{
          tone: 'weak',
          label: 'L1 — Recognition',
          text: 'Not quite. This describes *what* an index is rather than *why* this query is slow without one.',
        }}
      />
    </div>
  );
}

/** A strong verdict on its own. */
export function Strong() {
  return (
    <div style={wrap}>
      <VerdictMsg
        item={{
          tone: 'strong',
          label: 'L4 — Analysis',
          text: 'Correct, and the reasoning generalises. You worked from the access pattern rather than from the schema, which is the habit worth keeping.',
        }}
      />
    </div>
  );
}

/** Markdown inside a verdict — lists and inline code are common in feedback. */
export function RichFeedback() {
  return (
    <div style={wrap}>
      <VerdictMsg
        item={{
          tone: 'partial',
          label: 'L2 — Recall',
          text:
            'Two of the three are right.\n\n' +
            '- `WHERE user_id = ?` — correct, the composite index serves this\n' +
            '- `ORDER BY created_at` — correct, and it avoids the sort\n' +
            '- `WHERE status = ?` — **not** served; `status` is not a leading column\n\n' +
            'Re-read the third one and tell me what index would fix it.',
        }}
      />
    </div>
  );
}

/** Without a label — the pill still carries the tone. */
export function NoLabel() {
  return (
    <div style={wrap}>
      <VerdictMsg item={{ tone: 'weak', text: 'That is the definition, not the reason. Try again from the query plan.' }} />
    </div>
  );
}
