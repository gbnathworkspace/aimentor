import React from 'react';
import { MentorQuestionCard } from 'mentorman-web';

// When a mentor turn is a question, it renders as a card instead of a bubble:
// spark badge, bold heading, supporting body. The component splits `text` on the
// first blank line — everything before it is the heading, everything after is
// the body — so the variants below are really variants of that one input.

const wrap: React.CSSProperties = { maxWidth: 620 };

/** Heading plus context, the shape the mentor is prompted to produce. */
export function Default() {
  return (
    <div style={wrap}>
      <MentorQuestionCard text={"What do you want to be able to do with SQL that you can't do today?\n\nBe concrete if you can — \"write a report query without help\" tells me more than \"get better at SQL\"."} />
    </div>
  );
}

/** No blank line — the whole message becomes the heading. */
export function HeadingOnly() {
  return (
    <div style={wrap}>
      <MentorQuestionCard text="Before we start — how much time per week can you realistically give this?" />
    </div>
  );
}

/** Markdown in the body: the heading strips bold, the body renders it. */
export function RichBody() {
  return (
    <div style={wrap}>
      <MentorQuestionCard
        text={
          '**Which of these is closest to where you are stuck?**\n\n' +
          'Pick the one that feels most familiar:\n\n' +
          '- You can read a query but not write one from scratch\n' +
          '- You can write one but not tell why it is slow\n' +
          '- You can read `EXPLAIN` output but not act on it\n\n' +
          'If none fit, describe it in your own words.'
        }
      />
    </div>
  );
}

/** A long body — checks that the card grows rather than clipping. */
export function LongContext() {
  return (
    <div style={wrap}>
      <MentorQuestionCard
        text={
          'How would you decide whether this table needs an index at all?\n\n' +
          'Assume the table has about half a million rows and grows by roughly two thousand a day. ' +
          'Reads happen on every page load; writes happen once per user action. There is already a ' +
          'primary key on `id`, and the query in question filters on `user_id` and sorts by `created_at`.\n\n' +
          'I am less interested in the answer than in how you get there — walk me through what you would look at first.'
        }
      />
    </div>
  );
}
