import React from 'react';
import { Icon } from 'mentorman-web';

// The full IconName union from src/components/mentorman/icons.tsx. Kept in the
// same order as the source so a new icon added there is obvious by its absence.
const NAMES = [
  'plus', 'chart', 'gear', 'send', 'arrowUp', 'check',
  'upload', 'code', 'spark', 'warn', 'x', 'arrowR',
  'back', 'target', 'clock', 'bolt', 'doc', 'dots', 'logout',
  'volume', 'stop', 'download', 'chevronDown', 'users', 'edit', 'user',
] as const;

const cell: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 8,
  padding: '14px 6px',
  borderRadius: 'var(--r-sm)',
  background: 'var(--card)',
  border: '1px solid var(--border-soft)',
  color: 'var(--fg-dim)',
};

const caption: React.CSSProperties = {
  fontFamily: 'var(--mono)',
  fontSize: 9.5,
  color: 'var(--muted)',
  letterSpacing: '0.02em',
};

/** Every icon in the set, at the default 16px. */
export function AllIcons() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: 8 }}>
      {NAMES.map((n) => (
        <div key={n} style={cell}>
          <Icon name={n} size={18} />
          <span style={caption}>{n}</span>
        </div>
      ))}
    </div>
  );
}

/** The size prop. Strokes are geometric, so they hold up small. */
export function Sizes() {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 26 }}>
      {[12, 16, 20, 28, 40].map((s) => (
        <div key={s} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, color: 'var(--fg)' }}>
          <Icon name="target" size={s} />
          <span style={caption}>{s}px</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Icons inherit `currentColor`, which is how they pick up accent, warn, info
 * and danger without a colour prop.
 */
export function Tones() {
  const tones: Array<[string, string]> = [
    ['var(--fg)', 'default'],
    ['var(--accent)', 'accent'],
    ['var(--warn)', 'warn'],
    ['var(--info)', 'info'],
    ['var(--danger)', 'danger'],
    ['var(--muted)', 'muted'],
  ];
  return (
    <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
      {tones.map(([c, label]) => (
        <div key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, color: c }}>
          <Icon name="spark" size={22} />
          <span style={caption}>{label}</span>
        </div>
      ))}
    </div>
  );
}

/** How icons actually appear in the product — inside buttons, beside labels. */
export function InButtons() {
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
      <button className="btn btn-accent btn-sm"><Icon name="plus" size={13} /> New Session</button>
      <button className="btn btn-sm"><Icon name="upload" size={13} /> Upload notes</button>
      <button className="btn btn-sm btn-ghost"><Icon name="chart" size={13} /> Skill graph</button>
      <button className="icon-btn" title="Settings"><Icon name="gear" /></button>
      <button className="icon-btn" title="Close"><Icon name="x" /></button>
    </div>
  );
}
