import React from 'react';
import { OnboardingBanner } from 'mentorman-web';

// A slim top-of-app reminder to finish onboarding. It self-hides once dismissed
// (sessionStorage), so the dismissed state has no static render — only the
// visible state is previewable.

const noop = () => {};

/** The banner as it first appears. */
export function Default() {
  return (
    <div style={{ width: 720 }}>
      <OnboardingBanner onComplete={noop} onDismiss={noop} />
    </div>
  );
}

/** Constrained width — checks that the text and the dismiss control reflow. */
export function Narrow() {
  return (
    <div style={{ width: 420 }}>
      <OnboardingBanner onComplete={noop} onDismiss={noop} />
    </div>
  );
}

/** Pinned above app content, which is the only place it renders. */
export function AboveContent() {
  return (
    <div style={{ width: 720, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <OnboardingBanner onComplete={noop} onDismiss={noop} />
      <div
        style={{
          padding: 20,
          background: 'var(--card)',
          border: '1px solid var(--border-soft)',
          borderRadius: 'var(--r)',
          color: 'var(--muted)',
          fontSize: 13,
        }}
      >
        Session content sits below the banner.
      </div>
    </div>
  );
}
