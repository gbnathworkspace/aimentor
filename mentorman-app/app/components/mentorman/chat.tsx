'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing } from './ui';
import { SESSIONS, SEEDS, MODES, type MessageItem, type ModeId, type ToneId, type Topic } from './data';
import type { SkillNode } from '@/lib/mentorman-api';

function ModeBar({ mode, onMode }: { mode: ModeId; onMode: (m: ModeId) => void }) {
  return (
    <div className="modes" role="tablist">
      {MODES.map(m => (
        <div key={m.id} className={`mode-tab ${mode === m.id ? 'active' : ''}`}
             onClick={() => onMode(m.id)} title={m.blurb}>
          {m.label}
        </div>
      ))}
    </div>
  );
}

function Composer({ mode, tone, onSend, busy }: {
  mode: ModeId;
  tone: ToneId;
  onSend: (text: string) => void;
  busy: boolean;
}) {
  const [val, setVal] = useState('');
  const [focus, setFocus] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  const grow = () => {
    const el = ref.current;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 180) + 'px'; }
  };

  const submit = () => {
    const t = val.trim();
    if (!t || busy) return;
    setVal('');
    if (ref.current) ref.current.style.height = 'auto';
    onSend(t);
  };

  const isEval = mode === 'evaluation';
  return (
    <div className="composer">
      {isEval && (
        <div className="eval-flag"><span className="dot" /> Evaluation mode — your answer is graded</div>
      )}
      <div className="composer-inner">
        <div className={`composer-box ${focus ? 'focus' : ''}`}>
          <textarea
            ref={ref} value={val} rows={1}
            placeholder={isEval ? 'Type your answer…' : 'Reply to your mentor…'}
            onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
            onChange={e => { setVal(e.target.value); grow(); }}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          />
          <div className="composer-tools">
            <button className="tool-btn" title="Attach">+</button>
            <button className="tool-btn" title="Code block">{'</>'}</button>
            <div className="spacer" />
            <span className="tag" style={{ marginRight: 2 }}>mode: {mode}</span>
            <button className="send-btn" onClick={submit} disabled={busy || !val.trim()} title="Send">
              <Icon name={isEval ? 'arrowUp' : 'send'} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

type Alert = { id: string; kind: 'warn' | 'good'; type: string; text: string; cta?: string };

function deriveAlerts(topics: Topic[]): Alert[] {
  const alerts: Alert[] = [];
  const worst = [...topics].sort((a, b) => b.gap - a.gap)[0];
  if (worst && worst.gap >= 40) {
    alerts.push({
      id: 'gap-' + worst.name,
      kind: 'warn',
      type: 'Biggest gap',
      text: `${worst.name} has a ${worst.gap}% gap — it's your highest priority right now.`,
      cta: 'Review plan',
    });
  }
  return alerts;
}

function AlertStack({ topics, onReview }: { topics: Topic[]; onReview: () => void }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const all = deriveAlerts(topics).filter(a => !dismissed.has(a.id));
  if (!all.length) return null;
  return (
    <div className="alert-stack">
      {all.map(a => (
        <div key={a.id} className={`alert ${a.kind}`}>
          <div className="a-ico"><Icon name={a.kind === 'warn' ? 'warn' : 'check'} /></div>
          <div className="a-body">
            <div className="a-type">{a.type}</div>
            <div className="a-text">{a.text}</div>
          </div>
          <div className="a-actions">
            {a.cta && <button className="btn btn-sm btn-ghost" onClick={onReview}>{a.cta}</button>}
            <button className="a-dismiss" title="Dismiss" onClick={() => setDismissed(s => new Set(s).add(a.id))}>
              <Icon name="x" size={13} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

const DRAFT_KEY = 'mentorman_draft';

export function ChatPanel({ sessionId, sessionTitle, mode, setMode, tone, onNav, onSessionSaved, topics = [] }: {
  sessionId: string;
  sessionTitle?: string;
  mode: ModeId;
  setMode: (m: ModeId) => void;
  tone: ToneId;
  onNav: (v: string) => void;
  onSessionSaved?: () => void;
  topics?: Topic[];
}) {
  const fallback = SESSIONS.find(s => s.id === sessionId) || { id: 'new', title: 'New session', cat: 'Topic', date: 'now' };
  const session = sessionTitle ? { ...fallback, title: sessionTitle } : fallback;
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  const greetedRef = useRef(false);

  useEffect(() => {
    greetedRef.current = false;
    const seed = SEEDS[sessionId] || [];

    // Restore from localStorage if resuming an unsaved session after a crash/reload
    if (sessionId === 'new' && seed.length === 0) {
      try {
        const raw = localStorage.getItem(DRAFT_KEY);
        if (raw) {
          const draft = JSON.parse(raw) as { msgs: MessageItem[] };
          if (draft.msgs?.length > 0) {
            setMsgs(draft.msgs);
            greetedRef.current = true; // skip greeting — conversation already started
            return;
          }
        }
      } catch {}
    }

    setMsgs([]);
    const timers: ReturnType<typeof setTimeout>[] = [];
    seed.forEach((m, i) => {
      timers.push(setTimeout(() => {
        setMsgs(prev => [...prev, { ...m, _id: 'seed' + i }]);
      }, 160 + i * 480));
    });
    return () => timers.forEach(clearTimeout);
  }, [sessionId]);

  // Auto-greet: when starting a fresh session with no seeds, get the first mentor message
  useEffect(() => {
    const seed = SEEDS[sessionId] || [];
    if (seed.length > 0 || greetedRef.current) return;
    greetedRef.current = true;
    setBusy(true);
    fetch('/api/mentor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic: session.title,
        mode,
        tone,
        messages: [{ role: 'user', content: '[session_start] Open the session with a short, sharp first message based on my profile and goal. Do not repeat what I said in onboarding — just get started.' }],
      }),
    })
      .then(r => r.json())
      .then(({ text: reply }) => {
        setMsgs([{ who: 'mentor', text: (reply || '').trim() || "Let's get started — what do you want to tackle first?", _id: 'greet0' }]);
        // Create active session in MongoDB now that we have a confirmed title and mode
        return fetch('/api/sessions', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ title: session.title, mode, topic: session.title, topic_category: session.cat }),
        }).then(r => r.ok ? r.json() : null)
          .then(data => { if (data?.sessionId) setBackendSessionId(data.sessionId); })
          .catch(() => {});
      })
      .catch(() => {
        setMsgs([{ who: 'mentor', text: "Let's get started — what do you want to tackle first?", _id: 'greet0' }]);
      })
      .finally(() => setBusy(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  // Persist active session to localStorage after every exchange so it survives a crash or reload
  useEffect(() => {
    if (sessionId !== 'new' || msgs.length === 0) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        title: session.title,
        cat: session.cat,
        msgs,
        savedAt: new Date().toISOString(),
      }));
    } catch {}
  }, [msgs, sessionId, session.title, session.cat]);

  const send = useCallback(async (text: string) => {
    const userMsg: MessageItem = { who: 'user', text, _id: 'u' + Date.now() };
    setMsgs(prev => [...prev, userMsg]);
    setBusy(true);
    try {
      const allHistory = [...msgs, userMsg]
        .filter(m => m.who === 'mentor' || m.who === 'user')
        .map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
      // Anthropic requires the first message to be from 'user' — drop any leading assistant turns
      const firstUser = allHistory.findIndex(m => m.role === 'user');
      const history = firstUser > 0 ? allHistory.slice(firstUser) : allHistory;
      const res = await fetch('/api/mentor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: session.title, mode, tone, messages: history }),
      });
      const { text: reply } = await res.json();
      setMsgs(prev => [...prev, { who: 'mentor', text: (reply || '').trim() || "Let me think about that differently — can you say more about where you're stuck?", _id: 'm' + Date.now() }]);
    } catch {
      setMsgs(prev => [...prev, { who: 'mentor', text: "I'm having trouble reaching my notes right now — try that again in a moment.", _id: 'm' + Date.now() }]);
    } finally {
      setBusy(false);
    }
  }, [msgs, mode, tone, session.title]);

  const endSession = useCallback(async () => {
    localStorage.removeItem(DRAFT_KEY);
    if (msgs.length < 2) { onNav('summary'); return; }

    const apiMessages = msgs
      .filter(m => m.who === 'mentor' || m.who === 'user')
      .map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));

    if (backendSessionId) {
      // Full save — messages + Haiku summary + skill_update extraction
      const ok = await fetch(`/api/sessions/${backendSessionId}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ messages: apiMessages, mode, topic: session.title }),
      }).then(r => r.ok).catch(() => false);
      if (ok) onSessionSaved?.();
    } else {
      // Fallback: no backendSessionId (session create failed) — create a minimal record
      const ok = await fetch('/api/sessions', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ title: session.title, mode, topic: session.title, topic_category: session.cat }),
      }).then(r => r.ok).catch(() => false);
      if (ok) onSessionSaved?.();
    }
    onNav('summary');
  }, [msgs, session, mode, onNav, onSessionSaved, backendSessionId]);

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">{session.title}</div>
          <div className="ph-sub">session · {session.cat.toLowerCase()} · {session.date}</div>
        </div>
        <div className="ph-right">
          <ModeBar mode={mode} onMode={setMode} />
          <button className="btn btn-sm btn-ghost" onClick={endSession} title="End session">End</button>
          <span className="pill ok"><span className="ind" /> active</span>
        </div>
      </div>

      <AlertStack topics={topics} onReview={() => onNav('dashboard')} />

      <div className="chat-body" ref={bodyRef}>
        <div className="chat-inner">
          {msgs.map((m, i) =>
            m.who === 'verdict'
              ? <VerdictMsg key={m._id || i} item={m as any} />
              : <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />
          )}
          {busy && <Typing />}
        </div>
      </div>

      <Composer mode={mode} tone={tone} onSend={send} busy={busy} />
    </div>
  );
}
