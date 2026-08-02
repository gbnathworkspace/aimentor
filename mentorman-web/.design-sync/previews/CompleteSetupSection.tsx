import React from 'react';
import { CompleteSetupSection } from 'mentorman-web';

// The settings-page prompt to finish profile setup: section label, explanatory
// copy, full-width accent CTA, and an optional dismiss control.

const noop = () => {};

/** Without onClose — no dismiss button, copy runs full width. */
export function Default() {
  return (
    <div style={{ width: 380 }}>
      <CompleteSetupSection onStartSetup={noop} />
    </div>
  );
}

/** With onClose — a × appears in the corner and the copy insets to clear it. */
export function Dismissible() {
  return (
    <div style={{ width: 380 }}>
      <CompleteSetupSection onStartSetup={noop} onClose={noop} />
    </div>
  );
}

/** Both, so the inset difference is visible. */
export function Variants() {
  return (
    <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
      <div style={{ width: 340 }}>
        <CompleteSetupSection onStartSetup={noop} />
      </div>
      <div style={{ width: 340 }}>
        <CompleteSetupSection onStartSetup={noop} onClose={noop} />
      </div>
    </div>
  );
}

/** In a narrow sidebar column, which is where settings renders it. */
export function InSidebarColumn() {
  return (
    <div
      style={{
        width: 280,
        padding: 16,
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r)',
      }}
    >
      <CompleteSetupSection onStartSetup={noop} onClose={noop} />
    </div>
  );
}
