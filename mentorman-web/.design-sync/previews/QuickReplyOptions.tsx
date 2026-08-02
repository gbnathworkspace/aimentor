import React from 'react';
import { QuickReplyOptions } from 'mentorman-web';

// The tappable answer rows under a question card: numbered options, always
// followed by a "type your own answer" row so a fixed list never forecloses a
// free-text reply, plus a close control to dismiss the whole card.

const noop = () => {};
const wrap: React.CSSProperties = { maxWidth: 560 };

/** The usual three-to-four option set. */
export function Default() {
  return (
    <div style={wrap}>
      <QuickReplyOptions
        options={[
          { title: 'Read a query but not write one', description: 'You can follow existing SQL but stall on a blank editor.' },
          { title: 'Write one but not tune it', description: 'Your queries work; you cannot tell why they are slow.' },
          { title: 'Read EXPLAIN but not act on it', description: 'You can get the plan out but not decide what to change.' },
        ]}
        onSelect={noop}
        onTypeOwn={noop}
        onClose={noop}
      />
    </div>
  );
}

/** Two options — the minimum useful list. */
export function TwoOptions() {
  return (
    <div style={wrap}>
      <QuickReplyOptions
        options={[
          { title: 'Keep going on indexing', description: 'Continue the current thread.' },
          { title: 'Switch to query planning', description: 'Move to the next focus area.' },
        ]}
        onSelect={noop}
        onTypeOwn={noop}
        onClose={noop}
      />
    </div>
  );
}

/** A longer list, and longer titles — checks wrapping and row rhythm. */
export function ManyOptions() {
  return (
    <div style={wrap}>
      <QuickReplyOptions
        options={[
          { title: 'Around 2 hours a week', description: 'Roughly one focused session.' },
          { title: 'Around 5 hours a week', description: 'Two or three sessions.' },
          { title: 'More than 8 hours a week', description: 'Most evenings.' },
          { title: 'It varies a lot week to week and I would rather not commit to a number', description: 'Irregular schedule.' },
          { title: 'I genuinely do not know yet', description: 'Decide later.' },
        ]}
        onSelect={noop}
        onTypeOwn={noop}
        onClose={noop}
      />
    </div>
  );
}

/** Composed under a question card, which is how it always appears in product. */
export function UnderAQuestion() {
  return (
    <div style={{ ...wrap, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="onb-card">
        <div className="onb-card-body">
          <div className="onb-card-heading">How much time per week can you give this?</div>
          <div className="onb-card-desc">An honest number beats an ambitious one — the plan is built around it.</div>
        </div>
      </div>
      <QuickReplyOptions
        options={[
          { title: 'About 2 hours', description: 'One focused session.' },
          { title: 'About 5 hours', description: 'Two or three sessions.' },
          { title: '8 hours or more', description: 'Most evenings.' },
        ]}
        onSelect={noop}
        onTypeOwn={noop}
        onClose={noop}
      />
    </div>
  );
}
