import React from 'react';
import { StyleNoteReplacementCard } from 'mentorman-web';

// Shown when a style_note proposal arrives but the profile already holds the
// maximum of five notes: the user must pick one to replace, or dismiss.
// `existingNotes` must be supplied — without it the component fetches the
// profile itself and would sit in its loading state forever in a preview.

const noop = () => {};

const existingNotes = [
  { category: 'explanation', note: 'Prefers analogies drawn from systems they already use' },
  { category: 'pacing', note: 'Wants to be stopped early when the approach is wrong' },
  { category: 'feedback', note: 'Responds better to a direct verdict than to hedging' },
  { category: 'format', note: 'Asks for code examples over prose descriptions' },
  { category: 'depth', note: 'Prefers one topic fully covered over three surveyed' },
];

/** The selection state with all five existing notes offered for replacement. */
export function Default() {
  return (
    <div style={{ maxWidth: 560 }}>
      <StyleNoteReplacementCard
        proposalId="p1"
        proposedNote={{
          category: 'explanation',
          note: 'Prefers worked examples before the general rule',
          source_quote: 'I only really get it once I see it done on a real case.',
        }}
        sourceFilename="learning-reflection.pdf"
        reason="Stated twice in the reflection document, both times unprompted."
        existingNotes={existingNotes}
        onReplace={noop}
        onDismiss={noop}
      />
    </div>
  );
}

/** Without a source quote — the proposed note renders on its own. */
export function NoSourceQuote() {
  return (
    <div style={{ maxWidth: 560 }}>
      <StyleNoteReplacementCard
        proposalId="p2"
        proposedNote={{ category: 'pacing', note: 'Wants shorter sessions, more often' }}
        sourceFilename="q3-goals.md"
        reason="Inferred from the stated weekly time budget."
        existingNotes={existingNotes}
        onReplace={noop}
        onDismiss={noop}
      />
    </div>
  );
}

/** Without a reason — the justification row is omitted. */
export function NoReason() {
  return (
    <div style={{ maxWidth: 560 }}>
      <StyleNoteReplacementCard
        proposalId="p3"
        proposedNote={{
          category: 'feedback',
          note: 'Wants the verdict first, then the explanation',
          source_quote: 'Tell me if I am wrong before you tell me why.',
        }}
        sourceFilename="learning-reflection.pdf"
        existingNotes={existingNotes}
        onReplace={noop}
        onDismiss={noop}
      />
    </div>
  );
}

/** A long proposed note and long existing notes — checks wrapping. */
export function LongContent() {
  return (
    <div style={{ maxWidth: 560 }}>
      <StyleNoteReplacementCard
        proposalId="p4"
        proposedNote={{
          category: 'explanation',
          note: 'Prefers to be walked through a concrete failing case end to end before any general principle is introduced, and finds abstract framing unhelpful as an opener',
          source_quote: 'Every time someone starts with the theory I lose the thread within a minute.',
        }}
        sourceFilename="learning-reflection-2026-03-08.pdf"
        reason="Appears three times across the reflection, twice as an explicit request and once as a complaint about a previous course."
        existingNotes={existingNotes}
        onReplace={noop}
        onDismiss={noop}
      />
    </div>
  );
}
