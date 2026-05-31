'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import { GapBar } from './ui';
import { TOPICS, type Topic } from './data';
import type { SkillNode } from '@/lib/mentorman-api';

function skillToTopic(s: SkillNode): Topic {
  const sig = (s.signals ?? {}) as Record<string, unknown>;
  return {
    name: s.topic,
    cat: (sig.cat as string) ?? 'General',
    cur: Number(s.current_level) || 0,
    req: Number(s.required_level) || 100,
    last: (sig.last as string) ?? '–',
    gap: Number(s.gap) || 0,
    level: (sig.level as string) ?? s.current_level,
    strong: (sig.strong as string[]) ?? [],
    weak: (sig.weak as string[]) ?? [],
  };
}

const gapClass = (g: number) => g >= 40 ? 'hi' : g >= 20 ? 'mid' : 'lo';

function Ring({ pct, animate }: { pct: number; animate: boolean }) {
  const r = 56, c = 2 * Math.PI * r;
  const [shown, setShown] = useState(animate ? 0 : pct);

  useEffect(() => {
    if (!animate) { setShown(pct); return; }
    let raf: number;
    const t0 = performance.now();
    const dur = 1200;
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(pct * e));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [pct, animate]);

  const off = c - (shown / 100) * c;
  return (
    <div className="ring-wrap">
      <svg width="132" height="132" viewBox="0 0 132 132">
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--accent-2)" />
            <stop offset="100%" stopColor="var(--accent)" />
          </linearGradient>
        </defs>
        <circle cx="66" cy="66" r={r} fill="none" stroke="var(--card-3)" strokeWidth="10" />
        <circle cx="66" cy="66" r={r} fill="none" stroke="url(#ringGrad)" strokeWidth="10"
                strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
                transform="rotate(-90 66 66)" style={{ filter: 'drop-shadow(0 0 6px var(--accent-glow))' }} />
      </svg>
      <div className="pct">
        <div className="num">{shown}%</div>
        <div className="lbl">ready</div>
      </div>
    </div>
  );
}

function TopicCard({ t, onStart, animate }: { t: Topic; onStart: (t: Topic) => void; animate: boolean }) {
  return (
    <div className="topic-card" onClick={() => onStart(t)}>
      <div className="tc-row">
        <div>
          <div className="tc-name">{t.name}</div>
          <div style={{ marginTop: 5 }}><span className="tag">{t.cat}</span></div>
        </div>
        <div>
          <div className={`tc-gap ${gapClass(t.gap)}`}>{t.gap}%</div>
          <div className="tc-last">last · {t.last}</div>
        </div>
      </div>
      <div>
        <div className="gapbar-labels">
          <span>current {t.cur}%</span>
          <span className="arrow">{t.level}</span>
          <span>req {t.req}%</span>
        </div>
        <GapBar cur={t.cur} req={t.req} animate={animate} />
      </div>
      <div className="area-tags">
        {t.strong.map(s => <span key={s} className="area-tag strong">{s}</span>)}
        {t.weak.map(w => <span key={w} className="area-tag weak">{w}</span>)}
      </div>
    </div>
  );
}

export function Dashboard({ onStartTopic }: { onStartTopic: (t: Topic) => void }) {
  const [animate, setAnimate] = useState(false);
  const [topics, setTopics] = useState<Topic[]>(TOPICS);

  useEffect(() => { const t = setTimeout(() => setAnimate(true), 60); return () => clearTimeout(t); }, []);

  useEffect(() => {
    fetch('/api/skills')
      .then(r => r.json())
      .then((data: SkillNode[]) => {
        if (Array.isArray(data) && data.length > 0) {
          setTopics(data.map(skillToTopic));
        }
      })
      .catch(() => {});
  }, []);

  const readiness = topics.length
    ? Math.round(topics.reduce((a, t) => a + Math.min(1, t.cur / t.req), 0) / topics.length * 100)
    : 0;
  const sortedGaps = [...topics].sort((a, b) => b.gap - a.gap).slice(0, 3);
  const avgGap = topics.length
    ? Math.round(topics.reduce((a, t) => a + t.gap, 0) / topics.length)
    : 0;

  return (
    <div className="dash">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">Your Progress</div>
          <div className="ph-sub">skill graph · updated today</div>
        </div>
        <div className="ph-right">
          <div className="countdown"><span className="ind" /> on track · <span className="strong">70 days</span></div>
        </div>
      </div>

      <div className="dash-body">
        <div className="dash-hero">
          <div style={{ flex: 1, minWidth: 220 }}>
            <h2 className="h">20 LPA SWE role</h2>
            <div className="sub"><b>Aug 2026</b> &nbsp;·&nbsp; 10 weeks left &nbsp;·&nbsp; 18 hrs/week</div>
          </div>
        </div>

        <div className="readiness">
          <Ring pct={readiness} animate={animate} />
          <div className="r-info">
            <div className="t">You&apos;re {readiness}% interview-ready</div>
            <div className="d">Graphs and Dynamic Programming are dragging the number down. Close those two and readiness jumps to an estimated <strong style={{ color: 'var(--accent)' }}>71%</strong>.</div>
            <div className="r-stats">
              <div className="r-stat"><div className="v">{avgGap}%</div><div className="l">avg gap</div></div>
              <div className="r-stat"><div className="v">{topics.length}</div><div className="l">topics tracked</div></div>
              <div className="r-stat"><div className="v" style={{ color: 'var(--accent)' }}>+13</div><div className="l">this week</div></div>
            </div>
          </div>
        </div>

        <div className="dash-label"><span>Topic coverage</span><span className="meta">{topics.length} topics</span></div>
        <div className="topic-grid">
          {topics.map(t => <TopicCard key={t.name} t={t} onStart={onStartTopic} animate={animate} />)}
        </div>

        <div className="divider" />

        <div className="dash-label"><span>Biggest gaps — click to start a Topic session</span></div>
        <div className="gap-pills">
          {sortedGaps.map((t, i) => (
            <div key={t.name} className="gap-pill" onClick={() => onStartTopic(t)}>
              <span className="rank">#{i + 1}</span>
              <span className="gname">{t.name}</span>
              <span className="gpct">{t.gap}%</span>
              <span className="arrow"><Icon name="arrowR" size={13} /></span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
