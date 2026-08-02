import React from 'react';
import { SkipButton } from 'mentorman-web';

// A ghost-styled "Skip" control used to step past an onboarding question.
// Two states only — enabled and disabled — so both fit in one card.

const noop = () => {};

/** Enabled, the default. */
export function Default() {
  return <SkipButton onSkip={noop} />;
}

/** Disabled — used while the previous answer is still saving. */
export function Disabled() {
  return <SkipButton onSkip={noop} disabled />;
}

/** Both states side by side. */
export function States() {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
      <SkipButton onSkip={noop} />
      <SkipButton onSkip={noop} disabled />
    </div>
  );
}

/** Where it actually sits — trailing the onboarding question's action row. */
export function InQuestionFooter() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        width: 460,
        padding: '12px 14px',
        background: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r)',
      }}
    >
      <span style={{ fontSize: 13, color: 'var(--muted)' }}>Question 3 of 7</span>
      <div style={{ display: 'flex', gap: 8 }}>
        <SkipButton onSkip={noop} />
        <button className="btn btn-accent btn-sm">Continue</button>
      </div>
    </div>
  );
}
