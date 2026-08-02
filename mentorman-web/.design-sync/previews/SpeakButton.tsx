import React from 'react';
import { SpeakButton } from 'mentorman-web';

// Read-aloud toggle backed by the browser's speech synthesis. It renders null
// where speechSynthesis is unavailable, and its `speaking` state is internal —
// only the idle state renders statically, so the cells below vary context
// rather than state.

/** The control on its own, at its natural size. */
export function Default() {
  return <SpeakButton text="Both memoize — they differ in what they cache." />;
}

/** Scaled up so the speaker glyph is legible in a card. */
export function Enlarged() {
  return (
    <div style={{ transform: 'scale(2.4)', transformOrigin: 'left center', width: 80, height: 40, display: 'flex', alignItems: 'center' }}>
      <SpeakButton text="Read this message aloud." />
    </div>
  );
}

/** Attached to a mentor bubble — its real home, bottom-right of the message. */
export function InBubble() {
  return (
    <div className="msg mentor" style={{ maxWidth: 520 }}>
      <div className="who"><img src="/logo-mark.svg" alt="" className="av" />Mentor</div>
      <div className="bubble">
        An index makes reads faster and writes slower. On a write-heavy table that trade is
        rarely worth it unless the read is on a hot path.
        <SpeakButton
          text="An index makes reads faster and writes slower."
          className="bubble-speak"
        />
      </div>
    </div>
  );
}

/** On a question card, where it uses the onb-card-speak placement instead. */
export function OnQuestionCard() {
  return (
    <div className="onb-card" style={{ maxWidth: 520 }}>
      <div className="onb-card-body">
        <div className="onb-card-heading">What are you hoping to get out of this?</div>
        <div className="onb-card-desc">A sentence is plenty — I will ask follow-ups.</div>
      </div>
      <SpeakButton text="What are you hoping to get out of this?" className="onb-card-speak" />
    </div>
  );
}
