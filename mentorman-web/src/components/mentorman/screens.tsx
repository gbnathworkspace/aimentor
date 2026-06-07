'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useClerk } from '@clerk/clerk-react';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { type MessageItem } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';

// ---------- Onboarding (conversational AI agent) ----------------

type ApiMsg = { role: 'user' | 'assistant'; content: string };
type CompletedProfile = { goal: string; deadline: string; overall_level: string; daily_availability: string };


export function Onboarding({ onFinish, userName }: { onFinish: (goal: string) => void; userName?: string }) {
  const { signOut } = useClerk();
  const [apiMsgs,    setApiMsgs]    = useState<ApiMsg[]>([]);
  const [thread,     setThread]     = useState<MessageItem[]>([]);
  const [busy,       setBusy]       = useState(false);
  const [done,       setDone]       = useState(false);
  const [profile,    setProfile]    = useState<CompletedProfile | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const [input,       setInput]       = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const step = done ? 4 : Math.min(3, Math.max(0, apiMsgs.filter(m => m.role === 'user').length - 1));
  const bodyRef  = useRef<HTMLDivElement>(null);
  const textaRef = useRef<HTMLTextAreaElement>(null);
  const started  = useRef(false);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread, busy, done]);

  // Kick off conversation on mount — send a silent "hi" to get the first question
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    callAgent([{ role: 'user', content: 'hi' }], []);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const attemptSave = async (p: CompletedProfile) => {
    setSaveFailed(false);
    const res = await fetch('/api/onboarding/complete', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(p),
    }).catch(() => null);
    if (!res?.ok) {
      setSaveFailed(true);
      return;
    }
    setSaveFailed(false);
    setTimeout(() => setDone(true), 400);
  };

  const callAgent = async (msgs: ApiMsg[], currentThread: MessageItem[]) => {
    setBusy(true);
    try {
      const res = await fetch('/api/onboarding/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ messages: msgs }),
      });
      const { text, complete, profile: p, suggestions: chips } = await res.json();

      const nextThread = text
        ? [...currentThread, { who: 'mentor' as const, text, _id: 'm' + Date.now() }]
        : currentThread;
      setThread(nextThread);
      setApiMsgs([...msgs, ...(text ? [{ role: 'assistant' as const, content: text }] : [])]);
      setSuggestions(Array.isArray(chips) ? chips : []);

      if (complete && p) {
        setProfile(p);
        await attemptSave(p);
      }
    } catch {
      setThread(prev => [...prev, { who: 'mentor', text: "Sorry, I lost connection for a second — try again.", _id: 'err' + Date.now() }]);
    } finally {
      setBusy(false);
    }
  };

  const sendText = (text: string) => {
    if (!text || busy || done) return;
    setSuggestions([]);
    const userMsg: ApiMsg        = { role: 'user', content: text };
    const threadMsg: MessageItem = { who: 'user', text, _id: 'u' + Date.now() };
    const nextThread = [...thread, threadMsg];
    const nextMsgs   = [...apiMsgs, userMsg];
    setThread(nextThread);
    callAgent(nextMsgs, nextThread);
  };

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    if (textaRef.current) textaRef.current.style.height = 'auto';
    sendText(text);
  };

  return (
    <div className="onb">
      <div className="onb-top">
        <Brand />
        {userName && (
          <span style={{ fontSize: 13, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
            hey, <span style={{ color: 'var(--fg-dim)', fontWeight: 600 }}>{userName}</span>
          </span>
        )}
        <div className="onb-progress">
          <span>setup</span>
          <div className="onb-steps">
            {[0,1,2,3].map(i => (
              <div key={i} className={`s ${i < step || done ? 'done' : i === step ? 'curr' : ''}`} />
            ))}
          </div>
        </div>
        <button
          className="icon-btn"
          title="Sign out"
          onClick={() => signOut({ redirectUrl: '/sign-in' })}
        >
          <Icon name="logout" />
        </button>
      </div>

      <div className="onb-stage" ref={bodyRef}>
        <div className="onb-thread">
          {thread.map((m, i) => (
            i === 0 && m.who === 'mentor'
              ? <div key={m._id} className="onb-q fade-up">{fmt(m.text)}</div>
              : <Bubble key={m._id} who={m.who as 'mentor' | 'user'} item={m} />
          ))}
          {busy && <Typing />}

          {saveFailed && profile && !done && (
            <div className="onb-save-error">
              <span>Couldn&apos;t save your profile — please check your connection.</span>
              <button
                className="btn btn-sm btn-accent"
                disabled={busy}
                onClick={() => attemptSave(profile)}
              >
                Retry
              </button>
            </div>
          )}

          {done && profile && (
            <div className="setup-card">
              <div className="badge"><span className="dot" /> Setup complete</div>
              <h3>You&apos;re all set.</h3>
              <div className="setup-lines">
                <div className="setup-line"><span className="k">goal</span><span className="v">{profile.goal}</span></div>
                <div className="setup-line"><span className="k">deadline</span><span className="v">{profile.deadline}</span></div>
                <div className="setup-line"><span className="k">availability</span><span className="v">{profile.daily_availability}</span></div>
              </div>
              <button className="btn btn-accent" style={{ width: '100%', height: 42 }} onClick={() => onFinish(profile.goal)}>
                Start your first session <Icon name="arrowR" size={15} />
              </button>
            </div>
          )}
        </div>
      </div>

      {!done && (
        <div className="onb-composer">
          <div className="onb-composer-inner">
            {!busy && suggestions.length > 0 && (
              <div className="onb-suggestions">
                {suggestions.map(r => (
                  <button key={r} className="onb-suggestion" onClick={() => sendText(r)}>{r}</button>
                ))}
              </div>
            )}
            <div className="composer-box">
              <textarea
                ref={textaRef}
                rows={1}
                value={input}
                placeholder="Reply to your mentor…"
                style={{ minHeight: 22 }}
                onChange={e => {
                  setInput(e.target.value);
                  const el = e.target as HTMLTextAreaElement;
                  el.style.height = 'auto';
                  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
                }}
              />
              <div className="composer-tools">
                <button className="tool-btn">+</button>
                <div className="spacer" />
                <span className="tag">onboarding</span>
                <button className="send-btn" onClick={send} disabled={busy || !input.trim()}>
                  <Icon name="send" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Session-end summary -----------------------------
export function SessionEnd({ onFollow, onBack }: { onFollow: () => void; onBack: () => void }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">BFS/DFS revision</div><div className="ph-sub">session ended · saved</div></div>
        <div className="ph-right"><span className="pill ok"><span className="ind" /> session saved</span></div>
      </div>
      <div className="se-body">
        <div className="se-inner">
          <div className="se-top">
            <div className="label">Session summary</div>
            <h2 className="title-lg">BFS/DFS revision</h2>
            <div className="meta">today · 36 min · session ended</div>
          </div>
          <div className="se-summary">
            <div className="label">Summary</div>
            <div className="body">
              Session saved. Your skill graph has been updated based on this conversation.
            </div>
          </div>
          <div className="se-actions">
            <button className="btn btn-accent" style={{ flex: 1, height: 42 }} onClick={onFollow}>Start follow-up session <Icon name="arrowR" size={15} /></button>
            <button className="btn btn-ghost" style={{ height: 42 }} onClick={onBack}>Back to sessions</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Settings ----------------------------------------
export function Settings({ profile, onReset, onSaved }: {
  profile: CoreProfile | null;
  onReset: () => void;
  onSaved: () => void;
}) {
  const [editGoal, setEditGoal] = useState(false);
  const [editDeadline, setEditDeadline] = useState(false);
  const [editAvail, setEditAvail] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const [goalVal, setGoalVal] = useState(profile?.goal ?? '');
  const [deadlineVal, setDeadlineVal] = useState(profile?.deadline ?? '');
  const [availVal, setAvailVal] = useState(profile?.daily_availability ?? '');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Sync form values when profile loads / changes
  useEffect(() => {
    setGoalVal(profile?.goal ?? '');
    setDeadlineVal(profile?.deadline ?? '');
    setAvailVal(profile?.daily_availability ?? '');
  }, [profile]);

  const save = async (field: Record<string, string>): Promise<boolean> => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await fetch('/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(field),
      });
      if (!res.ok) {
        setSaveError('Save failed — please try again');
        return false;
      }
      onSaved();
      return true;
    } catch {
      setSaveError('Connection error — please try again');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await fetch('/api/profile', { method: 'DELETE' });
      if (!res.ok) {
        setSaveError('Reset failed — please try again');
        setConfirmReset(false);
        return;
      }
      onReset();
    } catch {
      setSaveError('Connection error — please try again');
      setConfirmReset(false);
    } finally {
      setSaving(false);
    }
  };

  const deadlineDisplay = profile?.deadline
    ? new Date(profile.deadline).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
    : '—';

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">Profile &amp; Settings</div><div className="ph-sub">goal · availability · data</div></div>
      </div>
      <div className="set-body">
        <div className="set-inner">

          {saveError && (
            <div style={{ fontSize: 12, color: '#f87171', padding: '8px 12px', background: 'rgba(248,113,113,0.08)', borderRadius: 6, marginBottom: 8 }}>
              {saveError}
            </div>
          )}

          <div className="set-section">
            <div className="set-label">Goal</div>

            <div className="set-row">
              <div className="k">Goal</div>
              {editGoal ? (
                <div style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    className="num-input" style={{ flex: 1 }}
                    value={goalVal}
                    onChange={e => setGoalVal(e.target.value)}
                  />
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditGoal(false); setGoalVal(profile?.goal ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { if (await save({ goal: goalVal })) setEditGoal(false); }}>Save</button>
                </div>
              ) : (
                <>
                  <div className="v">{profile?.goal ?? '—'}</div>
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditGoal(true)}>Edit</button>
                </>
              )}
            </div>

            <div className="set-row">
              <div className="k">Target date</div>
              {editDeadline ? (
                <div style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    className="num-input" type="date" style={{ flex: 1 }}
                    value={deadlineVal}
                    onChange={e => setDeadlineVal(e.target.value)}
                  />
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditDeadline(false); setDeadlineVal(profile?.deadline ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { if (await save({ deadline: deadlineVal })) setEditDeadline(false); }}>Save</button>
                </div>
              ) : (
                <>
                  <div className="v">{deadlineDisplay}</div>
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditDeadline(true)}>Edit</button>
                </>
              )}
            </div>
          </div>

          <div className="set-section">
            <div className="set-label">Availability</div>
            <div className="avail-card">
              <div className="avail-top">
                <div className="main">{profile?.daily_availability ?? '—'}</div>
              </div>
              {editAvail ? (
                <div className="avail-form">
                  <div className="avail-field" style={{ flex: 1 }}>
                    <label>Daily availability</label>
                    <input
                      className="num-input" style={{ width: '100%' }}
                      value={availVal}
                      placeholder="e.g. 2 hrs weekdays, 4 on weekends"
                      onChange={e => setAvailVal(e.target.value)}
                    />
                  </div>
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditAvail(false); setAvailVal(profile?.daily_availability ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { if (await save({ daily_availability: availVal })) setEditAvail(false); }}>Save</button>
                </div>
              ) : (
                <button className="btn btn-sm btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setEditAvail(true)}>Edit</button>
              )}
            </div>
          </div>

          <div className="set-section">
            <div className="set-label">Data sources</div>
            <div style={{ color: 'var(--muted)', fontSize: 12, padding: '8px 0' }}>
              File ingestion is not yet active. Resume and LeetCode uploads coming soon.
            </div>
          </div>

          <div className="set-section">
            <div className="set-label danger">Danger zone</div>
            <div className="danger-card">
              {confirmReset ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>This will delete your profile and restart onboarding. Are you sure?</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="danger-btn" disabled={saving} onClick={handleReset}>Yes, reset everything</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <button className="danger-btn" onClick={() => setConfirmReset(true)}>Reset goal and skill graph</button>
                  <div className="danger-note">This clears your profile and restarts onboarding.</div>
                </>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

