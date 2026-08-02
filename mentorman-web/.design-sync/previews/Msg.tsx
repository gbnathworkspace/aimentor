import React from 'react';
import { Msg } from 'mentorman-web';

// Msg is the row primitive under every chat turn: it renders the who-line
// (mentor avatar from /logo-mark.svg, or a "Y" initial for the learner) and
// then whatever children you give it. Bubble, VerdictMsg and Typing all wrap it.

const bubble: React.CSSProperties = { maxWidth: 520 };

/** The two speakers, which is the whole variant axis. */
export function Speakers() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 620 }}>
      <Msg who="user">
        <div className="bubble" style={bubble}>What is the actual cost of an index on a write-heavy table?</div>
      </Msg>
      <Msg who="mentor">
        <div className="bubble" style={bubble}>
          Every insert has to update the index too, so writes get slower in proportion to how many
          indexes the table carries. On a write-heavy table that is the trade you are making.
        </div>
      </Msg>
    </div>
  );
}

/** Mentor turn on its own — avatar is the logo mark. */
export function MentorTurn() {
  return (
    <Msg who="mentor">
      <div className="bubble" style={bubble}>
        Let's slow down on that last step — you skipped the part where the transaction commits.
      </div>
    </Msg>
  );
}

/** Learner turn on its own — avatar is a lettered initial. */
export function LearnerTurn() {
  return (
    <Msg who="user">
      <div className="bubble" style={bubble}>Got it. So the rollback would undo the insert but not the file write?</div>
    </Msg>
  );
}

/**
 * Msg takes arbitrary children, so it also carries non-bubble content —
 * here a verdict-style panel composed by hand.
 */
export function CustomChildren() {
  return (
    <Msg who="mentor">
      <div
        style={{
          maxWidth: 520,
          padding: 14,
          borderRadius: 'var(--r)',
          background: 'var(--card-2)',
          border: '1px solid var(--accent-line)',
        }}
      >
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 8 }}>
          Checkpoint
        </div>
        <div style={{ color: 'var(--fg-dim)', lineHeight: 1.55 }}>
          You have covered transactions and isolation levels. Next session picks up at deadlocks.
        </div>
      </div>
    </Msg>
  );
}
