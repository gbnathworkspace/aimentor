'use client';

import React, { Fragment, useState, useEffect } from 'react';
import { useAuth } from '../../auth/useAuth';
import { Icon } from './icons';
import { SpeakButton } from './SpeakButton';
import { MODES, type Session } from './data';
import type { CoreProfile, SessionRecord } from '@/lib/mentorman-api';

// ---- tiny inline markdown: **bold**, *italic*, ~~strike~~, `code`, [links](url) ----
// Order matters: bold before italic so `**x**` isn't half-matched as italic first.
// No underscore-italic (_text_) — CommonMark disables intraword underscore emphasis
// for exactly the reason we'd otherwise hit: snake_case_variable would italicize.
const INLINE_RE = /(\*\*[^*]+\*\*|~~[^~]+~~|`[^`]+`|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)\s]+\))/;

function renderInlineSpans(line: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let rest = line;
  let key = 0;
  let m: RegExpMatchArray | null;
  while ((m = rest.match(INLINE_RE))) {
    const idx = m.index!;
    if (idx > 0) parts.push(rest.slice(0, idx));
    const tok = m[0];
    if (tok.startsWith('**')) parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith('~~')) parts.push(<del key={key++}>{tok.slice(2, -2)}</del>);
    else if (tok.startsWith('`')) parts.push(<code key={key++}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith('[')) {
      const linkMatch = tok.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)!;
      parts.push(<a key={key++} href={linkMatch[2]} target="_blank" rel="noopener noreferrer">{linkMatch[1]}</a>);
    } else parts.push(<em key={key++}>{tok.slice(1, -1)}</em>);
    rest = rest.slice(idx + tok.length);
  }
  if (rest) parts.push(rest);
  return parts;
}

function joinLines(lines: string[]): React.ReactNode {
  return lines.map((l, li) => (
    <Fragment key={li}>{li > 0 && <br />}{renderInlineSpans(l)}</Fragment>
  ));
}

const HR_RE = /^(-{3,}|\*{3,}|_{3,})$/;
const HEADER_RE = /^(#{1,6})\s+(.*)$/;
const UL_RE = /^[-*]\s+(.*)$/;
const OL_RE = /^\d+\.\s+(.*)$/;
const QUOTE_RE = /^>\s?(.*)$/;
const TABLE_SEP_CELL_RE = /^:?-{2,}:?$/;

// GFM tables: | a | b |  \n  |---|---|  \n  | 1 | 2 |
function splitTableRow(line: string): string[] {
  let l = line.trim();
  if (l.startsWith('|')) l = l.slice(1);
  if (l.endsWith('|')) l = l.slice(0, -1);
  return l.split('|').map(c => c.trim());
}
function isTableSeparatorRow(line: string): boolean {
  if (!line.includes('|') && !line.includes('-')) return false;
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every(c => TABLE_SEP_CELL_RE.test(c));
}

// ---- block-level markdown: headers, lists, tables, blockquotes, hr, paragraphs ----
function renderBlocks(text: string): React.ReactNode {
  const lines = text.split('\n');
  const nodes: React.ReactNode[] = [];
  let key = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === '') { i++; continue; }

    if (HR_RE.test(line.trim())) {
      nodes.push(<hr key={key++} />);
      i++;
      continue;
    }

    const header = line.match(HEADER_RE);
    if (header) {
      const Tag = `h${Math.min(header[1].length + 2, 6)}` as 'h3' | 'h4' | 'h5' | 'h6';
      nodes.push(<Tag key={key++}>{renderInlineSpans(header[2])}</Tag>);
      i++;
      continue;
    }

    if (QUOTE_RE.test(line)) {
      const quoted: string[] = [];
      while (i < lines.length && QUOTE_RE.test(lines[i])) {
        quoted.push(lines[i].replace(QUOTE_RE, '$1'));
        i++;
      }
      nodes.push(<blockquote key={key++}>{joinLines(quoted)}</blockquote>);
      continue;
    }

    if (UL_RE.test(line)) {
      const items: string[] = [];
      while (i < lines.length && UL_RE.test(lines[i])) {
        items.push(lines[i].match(UL_RE)![1]);
        i++;
      }
      nodes.push(
        <ul key={key++} className="task-aware">
          {items.map((it, li) => {
            const task = it.match(/^\[([ xX])\]\s+(.*)$/);
            if (!task) return <li key={li}>{renderInlineSpans(it)}</li>;
            const checked = task[1].toLowerCase() === 'x';
            return (
              <li key={li} className="task-item">
                <input type="checkbox" checked={checked} disabled readOnly />
                <span className={checked ? 'task-done' : undefined}>{renderInlineSpans(task[2])}</span>
              </li>
            );
          })}
        </ul>
      );
      continue;
    }

    if (OL_RE.test(line)) {
      const items: string[] = [];
      while (i < lines.length && OL_RE.test(lines[i])) {
        items.push(lines[i].match(OL_RE)![1]);
        i++;
      }
      nodes.push(<ol key={key++}>{items.map((it, li) => <li key={li}>{renderInlineSpans(it)}</li>)}</ol>);
      continue;
    }

    // Table: a row containing `|` immediately followed by a `|---|---|` separator row
    if (line.includes('|') && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
      const header = splitTableRow(line);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim() !== '' && lines[i].includes('|')) {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      nodes.push(
        <table key={key++}>
          <thead><tr>{header.map((c, ci) => <th key={ci}>{renderInlineSpans(c)}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>{r.map((c, ci) => <td key={ci}>{renderInlineSpans(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      );
      continue;
    }

    // Paragraph: consecutive plain lines until a blank line or a block starts
    const paraLines: string[] = [];
    while (
      i < lines.length && lines[i].trim() !== '' &&
      !HR_RE.test(lines[i].trim()) && !HEADER_RE.test(lines[i]) &&
      !QUOTE_RE.test(lines[i]) && !UL_RE.test(lines[i]) && !OL_RE.test(lines[i]) &&
      !(lines[i].includes('|') && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1]))
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    nodes.push(<p key={key++}>{joinLines(paraLines)}</p>);
  }

  return nodes;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="codeblock">
      <div className="codeblock-head">
        <span className="codeblock-lang">{lang || 'text'}</span>
        <button className="codeblock-copy" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

// Splits on fenced ```lang\n...\n``` blocks and renders each as a CodeBlock,
// running everything else through the block-level markdown handling above.
const FENCE_RE = /```(\w*)\n([\s\S]*?)```/g;

export function fmt(text: string | null | undefined): React.ReactNode {
  if (text == null) return null;
  const str = String(text);
  if (!str.includes('```')) return renderBlocks(str);

  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  FENCE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = FENCE_RE.exec(str))) {
    if (m.index > lastIndex) nodes.push(<Fragment key={key++}>{renderBlocks(str.slice(lastIndex, m.index))}</Fragment>);
    nodes.push(<CodeBlock key={key++} lang={m[1]} code={m[2].replace(/\n$/, '')} />);
    lastIndex = FENCE_RE.lastIndex;
  }
  if (lastIndex < str.length) nodes.push(<Fragment key={key++}>{renderBlocks(str.slice(lastIndex))}</Fragment>);
  return nodes;
}

// ---- Brand -------------------------------------------------
export function Brand({ small }: { small?: boolean }) {
  return (
    <div className="brand">
      <img src="/logo-full.svg" alt="MentorMan" className="brand-logo" style={small ? { height: 20 } : {}} />
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
        {who === 'mentor'
          ? <img src="/logo-mark.svg" alt="" className="av" />
          : <span className="av">Y</span>}
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
        {item.nudge && (
          <div className="nudge">
            <div className="label">Nudge</div>
            {fmt(item.nudge)}
          </div>
        )}
        {who === 'mentor' && item.text && <SpeakButton text={item.text} className="bubble-speak" />}
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
  const focusSummary = profile?.learning_context_detail?.label
    || (profile?.focus_areas?.length ? profile.focus_areas.join(', ') : null);
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
            <div className="sub">{focusSummary ?? '—'}</div>
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
