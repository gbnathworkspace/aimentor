'use client';

import React, { Fragment, useState, useEffect } from 'react';
import { Icon } from './icons';
import { MODES, type Session } from './data';
import type { CoreProfile, SessionRecord } from '@/lib/mentorman-api';

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

function daysLeft(deadline: string | undefined): number | null {
  if (!deadline) return null;
  const diff = new Date(deadline).getTime() - Date.now();
  return Math.max(0, Math.round(diff / 86_400_000));
}

function apiSessionToSession(r: SessionRecord): Session {
  return { id: r.session_id, title: r.title, cat: r.type, date: r.date };
}

// ---- Session skeleton (loading placeholder) ----------------
function SessionSkeleton() {
  return (
    <div className="session" style={{ pointerEvents: 'none', opacity: 0.45 }}>
      <div className="s-row1">
        <span className="s-title" style={{ background: 'var(--card-3)', borderRadius: 4, color: 'transparent', userSelect: 'none' }}>Loading session title...</span>
      </div>
      <div className="s-row2">
        <span className="tag" style={{ background: 'var(--card-3)', color: 'transparent', userSelect: 'none' }}>Topic</span>
      </div>
    </div>
  );
}

// ---- Sidebar -----------------------------------------------
export function Sidebar({ view, activeSession, onPickSession, onNav, onNew, profile, userName }: {
  view: string;
  activeSession: string;
  onPickSession: (id: string, type?: string) => void;
  onNav: (v: string) => void;
  onNew: () => void;
  profile?: CoreProfile | null;
  userName?: string;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch('/api/sessions?limit=30')
      .then(r => r.json())
      .then((data: SessionRecord[]) => {
        if (Array.isArray(data) && data.length > 0) {
          setSessions(data.map(apiSessionToSession));
        } else {
          setSessions([]);
        }
      })
      .catch(() => { setSessions([]); })
      .finally(() => setLoading(false));
  }, []);

  const days = daysLeft(profile?.deadline);
  const displayName = userName || profile?.email?.split('@')[0] || 'You';
  const initial = displayName[0]?.toUpperCase() ?? 'Y';

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

      <div className="sb-section"><span>Sessions</span><span className="count">{loading ? '…' : sessions.length}</span></div>
      <div className="session-list">
        {loading ? (
          <>
            <SessionSkeleton />
            <SessionSkeleton />
            <SessionSkeleton />
          </>
        ) : sessions.length === 0 ? (
          <div style={{ padding: '20px 12px', textAlign: 'center' }}>
            <div style={{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.5, marginBottom: 12 }}>
              No sessions yet.<br />Start your first conversation.
            </div>
            <button className="btn btn-sm btn-ghost" onClick={onNew} style={{ width: '100%' }}>
              <Icon name="plus" size={13} /> New Session
            </button>
          </div>
        ) : (
          sessions.map(s => {
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
          })
        )}
      </div>

      {/* Clickable footer → Profile / Settings */}
      <button
        className="sb-foot"
        onClick={() => onNav('settings')}
        title="View profile & settings"
        style={{ cursor: 'pointer', background: 'none', border: 'none', width: '100%', textAlign: 'left' }}
      >
        <div className="avatar">{initial}</div>
        <div>
          <div className="who">{displayName}</div>
          <div className="sub">
            {profile?.goal ?? '—'}
            {days !== null ? ` · ${days} days left` : ''}
          </div>
        </div>
      </button>
    </div>
  );
}
