import React from 'react';
import { SummaryBlockIndicator } from 'mentorman-web';

// Marks where earlier conversation was compacted into a summary. Renders as a
// collapsed pill that expands on click — the expanded state is click-driven, so
// only the collapsed state renders statically (noted in NOTES.md).

const summary =
  'Across the first eleven turns the learner moved from not recognising what an index does ' +
  'to correctly predicting which of three queries a composite index would serve. Remaining ' +
  'gap: reading EXPLAIN output and deciding what to change from it.';

const wrap: React.CSSProperties = { maxWidth: 560 };

/** A multi-day compaction — the range renders as "Mar 3 – Mar 8, 2026". */
export function Default() {
  return (
    <div style={wrap}>
      <SummaryBlockIndicator
        summaryBlock={{
          type: 'summary',
          id: 'sum_1',
          summary,
          compactedRange: { from: '2026-03-03T09:12:00Z', to: '2026-03-08T17:40:00Z' },
          messageCount: 24,
          tokenCount: 8120,
        }}
      />
    </div>
  );
}

/** Same calendar day — the range collapses to a single date. */
export function SameDay() {
  return (
    <div style={wrap}>
      <SummaryBlockIndicator
        summaryBlock={{
          type: 'summary',
          id: 'sum_2',
          summary,
          compactedRange: { from: '2026-03-08T09:00:00Z', to: '2026-03-08T11:30:00Z' },
          messageCount: 12,
          tokenCount: 3400,
        }}
      />
    </div>
  );
}

/** Singular label — "1 earlier message summarized", not "messages". */
export function SingleMessage() {
  return (
    <div style={wrap}>
      <SummaryBlockIndicator
        summaryBlock={{
          type: 'summary',
          id: 'sum_3',
          summary,
          compactedRange: { from: '2026-02-19T14:00:00Z', to: '2026-02-19T14:05:00Z' },
          messageCount: 1,
          tokenCount: 180,
        }}
      />
    </div>
  );
}

/** In conversation flow — it sits between turns, marking the seam. */
export function InConversation() {
  return (
    <div style={{ ...wrap, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <SummaryBlockIndicator
        summaryBlock={{
          type: 'summary',
          id: 'sum_4',
          summary,
          compactedRange: { from: '2026-03-03T09:12:00Z', to: '2026-03-08T17:40:00Z' },
          messageCount: 24,
          tokenCount: 8120,
        }}
      />
      <div className="msg user">
        <div className="who"><span className="av">Y</span>You</div>
        <div className="bubble">Picking up where we left off — how do I read the cost numbers?</div>
      </div>
    </div>
  );
}
