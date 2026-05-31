'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing } from './ui';
import { SESSIONS, SEEDS, MODES, mentorSystemPrompt, type MessageItem, type ModeId, type ToneId, type Topic } from './data';
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

export function ChatPanel({ sessionId, mode, setMode, tone, onNav, topics = [] }: {
  sessionId: string;
  mode: ModeId;
  setMode: (m: ModeId) => void;
  tone: ToneId;
  onNav: (v: string) => void;
  topics?: Topic[];
}) {
  const session = SESSIONS.find(s => s.id === sessionId) || { id: 'new', title: 'New session', cat: 'Topic', date: 'now' };
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const seed = SEEDS[sessionId] || [];
    setMsgs([]);
    const timers: ReturnType<typeof setTimeout>[] = [];
    seed.forEach((m, i) => {
      timers.push(setTimeout(() => {
        setMsgs(prev => [...prev, { ...m, _id: 'seed' + i }]);
      }, 160 + i * 480));
    });
    return () => timers.forEach(clearTimeout);
  }, [sessionId]);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  const send = useCallback(async (text: string) => {
    const userMsg: MessageItem = { who: 'user', text, _id: 'u' + Date.now() };
    setMsgs(prev => [...prev, userMsg]);
    setBusy(true);
    try {
      const history = [...msgs, userMsg]
        .filter(m => m.who === 'mentor' || m.who === 'user')
        .map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
      const res = await fetch('/api/mentor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system: mentorSystemPrompt(mode, tone, session.title), messages: history }),
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
    if (msgs.length < 2) { onNav('summary'); return; }
    const summary = msgs
      .filter(m => m.who === 'mentor' || m.who === 'user')
      .slice(-6)
      .map(m => `${m.who === 'mentor' ? 'Mentor' : 'You'}: ${m.text}`)
      .join('\n');
    await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic: session.title,
        topic_category: session.cat,
        type: session.cat,
        date: new Date().toISOString().slice(0, 10),
        title: session.title,
        summary,
      }),
    }).catch(() => {});
    onNav('summary');
  }, [msgs, session, onNav]);

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
