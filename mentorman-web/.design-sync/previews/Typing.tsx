import React from 'react';
import { Typing } from 'mentorman-web';

// The mentor's pending-response indicator: three animated dots inside a bubble,
// with an optional label naming what the mentor is doing.

/** Bare indicator — no label, tight bubble. */
export function Default() {
  return <Typing />;
}

/** Labelled, for the longer waits where the user deserves to know why. */
export function WithLabel() {
  return <Typing label="Thinking through your answer…" />;
}

/** The labels the product actually uses, stacked. */
export function Labels() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Typing />
      <Typing label="Reading your document…" />
      <Typing label="Searching the web…" />
      <Typing label="Reviewing your last three sessions…" />
    </div>
  );
}

/** In conversation flow, after a learner turn. */
export function InConversation() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 620 }}>
      <div className="msg user">
        <div className="who"><span className="av">Y</span>You</div>
        <div className="bubble">I think it's because the index is on the wrong column — is that right?</div>
      </div>
      <Typing label="Checking your reasoning…" />
    </div>
  );
}
