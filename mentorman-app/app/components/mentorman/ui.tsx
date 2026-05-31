'use client';

import React, { Fragment, useState, useEffect } from 'react';
import { Icon } from './icons';
import { SESSIONS, MODES, type Session } from './data';
import type { SessionRecord } from '@/lib/mentorman-api';

// ---- tiny inline markdown: **bold**, `code`, \n ------------
export function fmt(text: string | null | undefined): React.ReactNode {
  if (text == null) return null;
  const lines = String(text).split('\n');
  return lines.map((line, li) => {
    const parts: React.ReactNode[] = [];
    let rest = line;
    let key = 0;
    const re = /(\*\*[^*]+\*\*|`[^`]+`)/;
    let m: RegExpMatchArray | null;
    while ((m = rest.match(re))) {
      const idx = m.index!;
      if (idx > 0) parts.push(rest.slice(0, idx));
      const tok = m[0];
      if (tok.startsWith('**')) parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);
      else parts.push(<code key={key++}>{tok.slice(1, -1)}</code>);
      rest = rest.slice(idx + tok.length);
    }
    if (rest) parts.push(rest);
    return <Fragment key={li}>{li > 0 && <br />}{parts}</Fragment>;
  });
}

// ---- Brand -------------------------------------------------
export function Brand({ small }: { small?: boolean }) {
  return (
    <div className="brand">
      <div className="brand-mark" style={small ? { width: 24, height: 24, fontSize: 12 } : {}}>M</div>
      {!small && <div className="brand-name">Mentor<span className="dim">Man</span></div>}
    </div>
  );
}

// ---- Message block -----------------------------------------
export function Msg({ who, children, delay = 0, style }: {
  who: 'mentor' | 'user';
  children: React.ReactNode;
  delay?: number;
  style?: React.CSSProperties;
}) {
  return (
    <div className={`msg ${who}`} style={{ animationDelay: `${delay}ms`, ...style }}>
      <div className="who">
        <span className="av">{who === 'mentor' ? 'M' : 'Y'}</span>
        {who === 'mentor' ? 'Mentor' : 'You'}
      </div>
      {children}
    </div>
  );
}

export function Bubble({ who, item, delay }: {
  who: 'mentor' | 'user';
  item: { text: string; label?: string; code?: string; nudge?: string };
  delay?: number;
}) {
  return (
    <Msg who={who} delay={delay}>
      {item.label && (
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', margin: '0 4px 6px' }}>
          {item.label}
        </div>
      )}
      <div className="bubble">
        {fmt(item.text)}
        {item.code && <div className="codeblock" dangerouslySetInnerHTML={{ __html: item.code }} />}
        {item.nudge && (
          <div className="nudge">
            <div className="label">Nudge</div>
            {fmt(item.nudge)}
          </div>
        )}
      </div>
    </Msg>
  );
}

export function VerdictMsg({ item, delay }: {
  item: { tone: 'strong' | 'partial' | 'weak'; label?: string; text: string };
  delay?: number;
}) {
  return (
    <Msg who="mentor" delay={delay}>
      <div className="verdict" style={{ maxWidth: 'none' }}>
        <div className="v-top">
          <span className={`verdict-tag ${item.tone}`}>
            {item.tone === 'strong' ? '✓ Strong' : item.tone === 'partial' ? '△ Partial' : '✕ Weak'}
          </span>
          <span className="v-lvl">{item.label}</span>
        </div>
        <div className="v-fb">{fmt(item.text)}</div>
      </div>
    </Msg>
  );
}

export function Typing() {
  return (
    <Msg who="mentor">
      <div className="bubble" style={{ padding: 0 }}>
        <div className="typing"><span /><span /><span /></div>
      </div>
    </Msg>
  );
}

export function GapBar({ cur, req, animate }: { cur: number; req: number; animate?: boolean }) {
  const [w, setW] = React.useState(animate ? 0 : cur);
  React.useEffect(() => {
    if (!animate) { setW(cur); return; }
    const t = setTimeout(() => setW(cur), 120);
    return () => clearTimeout(t);
  }, [cur, animate]);
  return (
    <div className="gapbar">
      <div className="fill" style={{ width: w + '%' }} />
      <div className="req-mark" style={{ left: req + '%' }} />
    </div>
  );
}

function apiSessionToSession(r: SessionRecord): Session {
  return { id: r.session_id, title: r.title, cat: r.type, date: r.date };
}

// ---- Sidebar -----------------------------------------------
export function Sidebar({ view, activeSession, onPickSession, onNav, onNew, profile }: {
  view: string;
  activeSession: string;
  onPickSession: (id: string, type?: string) => void;
  onNav: (v: string) => void;
  onNew: () => void;
  profile?: { goal?: string; deadline?: string } | null;
}) {
  const [sessions, setSessions] = useState<Session[]>(SESSIONS);

  useEffect(() => {
    fetch('/api/sessions?limit=30')
      .then(r => r.json())
      .then((data: SessionRecord[]) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data.map(apiSessionToSession));
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="sidebar">
      <div className="sb-head">
        <Brand />
        <div style={{ display: 'flex', gap: 4 }}>
          <button className={`icon-btn ${view === 'settings' ? 'on' : ''}`} title="Settings" onClick={() => onNav('settings')}>
            <Icon name="gear" />
          </button>
        </div>
      </div>

      <div className="sb-actions">
        <button className="new-session" onClick={onNew}>
          <Icon name="plus" size={15} /> New Session
        </button>
        <button className={`sb-nav-icon ${view === 'dashboard' ? 'on' : ''}`} title="Skill graph" onClick={() => onNav('dashboard')}>
          <Icon name="chart" size={17} />
        </button>
      </div>

      <div className="sb-section"><span>Sessions</span><span className="count">{sessions.length}</span></div>
      <div className="session-list">
        {sessions.map(s => {
          const isActive = (view === 'chat' || view === 'evaluation' || view === 'summary') && activeSession === s.id;
          return (
            <div key={s.id} className={`session ${isActive ? 'active' : ''}`} onClick={() => onPickSession(s.id, s.cat)}>
              <div className="s-row1">
                <span className="s-title">{s.title}</span>
                <span className="s-date">{s.date}</span>
              </div>
              <div className="s-row2">
                <span className="tag">{s.cat}</span>
                {s.live && <span className="pill ok" style={{ height: 18, padding: '0 7px', fontSize: 9 }}><span className="ind" /> live</span>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="sb-foot">
        <div className="avatar">AK</div>
        <div>
          <div className="who">Arjun K.</div>
          <div className="sub">{profile?.goal ?? '20 LPA'} · {profile?.deadline ?? '70 days left'}</div>
        </div>
      </div>
    </div>
  );
}
