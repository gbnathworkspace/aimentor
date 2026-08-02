import React from 'react';
import { GapBar } from 'mentorman-web';

// GapBar is an 8px-tall track: `cur` fills it with the accent gradient, `req`
// drops a tick at the level the topic requires. It has no width of its own —
// it fills its parent, so every cell below gives it one.

function Row({ label, cur, req }: { label: string; cur: number; req: number }) {
  return (
    <div style={{ width: 420 }}>
      <div className="gapbar-labels">
        <span>{label}</span>
        <span className="arrow">{cur}% / needs {req}%</span>
      </div>
      <GapBar cur={cur} req={req} />
    </div>
  );
}

/** The canonical use: current level against the level the topic requires. */
export function Default() {
  return <Row label="SQL indexing" cur={62} req={80} />;
}

/** The gap closing — below, at, and past the requirement. */
export function Progression() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <Row label="Just started" cur={12} req={70} />
      <Row label="Halfway" cur={45} req={70} />
      <Row label="Nearly there" cur={66} req={70} />
      <Row label="Requirement met" cur={70} req={70} />
      <Row label="Past requirement" cur={92} req={70} />
    </div>
  );
}

/** A skill breakdown, which is how the dashboard stacks them. */
export function SkillBreakdown() {
  const skills: Array<[string, number, number]> = [
    ['Transactions', 78, 75],
    ['Indexing', 62, 80],
    ['Query planning', 34, 65],
    ['Replication', 15, 50],
  ];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {skills.map(([name, cur, req]) => (
        <Row key={name} label={name} cur={cur} req={req} />
      ))}
    </div>
  );
}

/** Edge values — an empty track and a full one. */
export function Bounds() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <Row label="Untouched" cur={0} req={60} />
      <Row label="Mastered" cur={100} req={60} />
    </div>
  );
}
