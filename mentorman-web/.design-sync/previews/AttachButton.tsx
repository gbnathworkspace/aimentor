import React from 'react';
import { AttachButton } from 'mentorman-web';

// The composer's attach trigger. Deliberately a plain "+" rather than an
// upload arrow so it does not read as a second Send button. It also renders a
// hidden <input type="file">, which is why the visible surface is just the button.

const noop = () => {};

/** Enabled, the default. */
export function Default() {
  return <AttachButton onSelect={noop} />;
}

/** Disabled — used while a message is in flight. */
export function Disabled() {
  return <AttachButton onSelect={noop} disabled />;
}

/** Both states, scaled up so the glyph is legible. */
export function States() {
  return (
    <div style={{ display: 'flex', gap: 30, alignItems: 'center', transform: 'scale(1.8)', transformOrigin: 'left center' }}>
      <AttachButton onSelect={noop} />
      <AttachButton onSelect={noop} disabled />
    </div>
  );
}

/** In the composer toolbar, which is the only place it appears. */
export function InComposer() {
  return (
    <div className="composer-box" style={{ width: 520 }}>
      <div style={{ color: 'var(--muted)', fontSize: 13, padding: '2px 2px 10px' }}>
        Ask a follow-up, or attach your notes…
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <AttachButton onSelect={noop} />
        <div style={{ marginLeft: 'auto' }}>
          <button className="btn btn-accent btn-sm">Send</button>
        </div>
      </div>
    </div>
  );
}
