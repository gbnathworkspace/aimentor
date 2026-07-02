'use client';

import React, { Fragment, useState, useEffect } from 'react';
import { useAuth } from '../../auth/useAuth';
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
  const ms = new Date(deadline).getTime();
  if (Number.isNaN(ms)) return null; // non-date deadline (e.g. "3 months") → no countdown
  return Math.max(0, Math.round((ms - Date.now()) / 86_400_000));
}

function relativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7)  return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return new Date(iso).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
}

function apiSessionToSession(r: SessionRecord): Session {
  return { id: r.session_id, title: r.title, cat: r.type, date: relativeDate(r.date) };
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
export function Sidebar({ view, activeSession, onPickSession, onNav, onNew, profile, userName, refreshKey }: {
  view: string;
  activeSession: string;
  onPickSession: (id: string, type?: string, title?: string) => void;
  onNav: (v: string) => void;
  onNew: () => void;
  profile?: CoreProfile | null;
  userName?: string;
  refreshKey?: number;
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
  }, [refreshKey]);

  const removeSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation(); // don't open the session when deleting it
    setSessions(prev => prev.filter(s => s.id !== id)); // optimistic
    try {
      await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    } catch {
      /* ignore — list refreshes on next load */
    }
  };

  const { logout } = useAuth();
  const days = daysLeft(profile?.deadline ?? undefined);
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
              <div key={s.id} className={`session ${isActive ? 'active' : ''}`} onClick={() => onPickSession(s.id, s.cat, s.title)}>
                <div className="s-row1">
                  <span className="s-title">{s.title}</span>
                  <span className="s-date">{s.date}</span>
                </div>
                <div className="s-row2">
                  <span className="tag">{s.cat}</span>
                  {s.live && <span className="pill ok" style={{ height: 18, padding: '0 7px', fontSize: 9 }}><span className="ind" /> live</span>}
                  <button
                    title="Delete chat"
                    aria-label="Delete chat"
                    onClick={(e) => removeSession(s.id, e)}
                    style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 2, lineHeight: 0, display: 'flex' }}
                  >
                    <Icon name="x" size={12} />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Clickable footer → Profile / Settings */}
      <div className="sb-foot" style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
        <button
          onClick={() => onNav('settings')}
          title="View profile & settings"
          style={{ cursor: 'pointer', background: 'none', border: 'none', flex: 1, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10, padding: 0, minWidth: 0 }}
        >
          <div className="avatar">{initial}</div>
          <div style={{ minWidth: 0 }}>
            <div className="who">{displayName}</div>
            <div className="sub">
              {profile?.goal ?? '—'}
              {days !== null ? ` · ${days} days left` : ''}
            </div>
          </div>
        </button>
        <button
          className="icon-btn"
          title="Sign out"
          onClick={() => logout()}
          style={{ flexShrink: 0 }}
        >
          <Icon name="logout" />
        </button>
      </div>
    </div>
  );
}
