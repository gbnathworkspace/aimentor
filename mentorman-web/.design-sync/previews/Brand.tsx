import React from 'react';
import { Brand } from 'mentorman-web';

// Brand renders the MentorMan wordmark from /logo-full.svg. That absolute path
// resolves at the web root, which is why logo-full.svg ships at the design
// system root — see .design-sync/NOTES.md.

/** Default size, as used in the sidebar header. */
export function Default() {
  return <Brand />;
}

/** `small` clamps the mark to 20px for dense chrome. */
export function Small() {
  return <Brand small />;
}

/** Both together, so the size difference is legible in one glance. */
export function Sizes() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>default</div>
        <Brand />
      </div>
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>small</div>
        <Brand small />
      </div>
    </div>
  );
}

/** In its real home — the sidebar header strip. */
export function InSidebarHeader() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 16px',
        width: 260,
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r)',
      }}
    >
      <Brand />
    </div>
  );
}
