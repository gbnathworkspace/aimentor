import React from 'react';
import { DocumentProposalCard } from 'mentorman-web';

// The card the mentor shows after reading an uploaded document: extracted L1
// profile changes, each accept/dismiss-able. It has four visually distinct
// states, driven entirely by props — no fetching — so all four render statically.

const noop = () => {};

const pending = [
  {
    id: 'p1',
    field: 'style_note',
    proposedValue: {
      category: 'explanation',
      note: 'Prefers worked examples before the general rule',
      source_quote: 'I only really get it once I see it done on a real case.',
    },
    reason: 'Stated twice in the reflection doc, both times unprompted.',
    sourceFilename: 'learning-reflection.pdf',
    status: 'pending' as const,
  },
  {
    id: 'p2',
    field: 'focus_areas',
    proposedValue: { value: 'Database indexing' },
    reason: 'Three of the five listed goals are query-performance related.',
    sourceFilename: 'q3-goals.md',
    status: 'pending' as const,
  },
  {
    id: 'p3',
    field: 'style_note',
    proposedValue: { category: 'pacing', note: 'Wants to be interrupted early when the approach is wrong' },
    reason: 'Explicit request in the closing paragraph.',
    sourceFilename: 'learning-reflection.pdf',
    status: 'pending' as const,
  },
];

/** The default state — proposals awaiting review, with the Apply All control. */
export function PendingReview() {
  return (
    <div style={{ maxWidth: 560 }}>
      <DocumentProposalCard
        jobId="job_8f2c"
        proposals={pending}
        onAccept={noop}
        onDismiss={noop}
        onAcceptAll={noop}
      />
    </div>
  );
}

/** A single pending proposal — no Apply All (it only appears above one). */
export function SingleProposal() {
  return (
    <div style={{ maxWidth: 560 }}>
      <DocumentProposalCard
        jobId="job_1a90"
        proposals={[pending[1]]}
        onAccept={noop}
        onDismiss={noop}
        onAcceptAll={noop}
      />
    </div>
  );
}

/** Every proposal actioned — the card collapses to a read-only tally. */
export function Resolved() {
  return (
    <div style={{ maxWidth: 560 }}>
      <DocumentProposalCard
        jobId="job_8f2c"
        proposals={[
          { ...pending[0], status: 'accepted' as const },
          { ...pending[1], status: 'accepted' as const },
          { ...pending[2], status: 'dismissed' as const },
        ]}
        onAccept={noop}
        onDismiss={noop}
        onAcceptAll={noop}
        onClose={noop}
      />
    </div>
  );
}

/** skipReview — changes were applied directly, shown as an informational summary. */
export function AppliedDirectly() {
  return (
    <div style={{ maxWidth: 560 }}>
      <DocumentProposalCard
        jobId="job_44b1"
        skipReview
        proposals={[
          { ...pending[0], status: 'accepted' as const },
          { ...pending[1], status: 'accepted' as const },
        ]}
        onAccept={noop}
        onDismiss={noop}
        onAcceptAll={noop}
        onClose={noop}
      />
    </div>
  );
}

/** Partial failure — some uploads could not be read, listed under the proposals. */
export function WithFailedFiles() {
  return (
    <div style={{ maxWidth: 560 }}>
      <DocumentProposalCard
        jobId="job_c7d3"
        proposals={[pending[0], pending[1]]}
        failedFiles={[
          { filename: 'scanned-notes.pdf', reason: 'No extractable text layer' },
          { filename: 'slides.key', reason: 'Unsupported file type' },
        ]}
        onAccept={noop}
        onDismiss={noop}
        onAcceptAll={noop}
      />
    </div>
  );
}
