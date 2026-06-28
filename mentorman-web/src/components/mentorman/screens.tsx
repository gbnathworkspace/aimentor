'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useClerk } from '@clerk/clerk-react';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { type MessageItem } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';
import { SkipButton } from './SkipButton';
import { SkipConfirmationDialog } from './SkipConfirmationDialog';
import { CompleteSetupSection } from './CompleteSetupSection';

// ---------- Onboarding (conversational AI agent) ----------------

type ApiMsg = { role: 'user' | 'assistant'; content: string };
type CompletedProfile = { goal: string; deadline: string | null; overall_level: string; daily_availability: string };

export interface OnboardingProps {
  onFinish: (goal: string) => void;
  userName?: string;
  deferred?: boolean;
  onAbandon?: () => void;
}

export function Onboarding({ onFinish, userName, deferred = false, onAbandon }: OnboardingProps) {
  const { signOut } = useClerk();
  const [apiMsgs,    setApiMsgs]    = useState<ApiMsg[]>([]);
  const [thread,     setThread]     = useState<MessageItem[]>([]);
  const [busy,       setBusy]       = useState(false);
  const [done,       setDone]       = useState(false);
  const [profile,    setProfile]    = useState<CompletedProfile | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const [input,       setInput]       = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);

  // Skip state
  const [showSkipDialog, setShowSkipDialog] = useState(false);
  const [skipLoading,    setSkipLoading]    = useState(false);
  const [skipError,      setSkipError]      = useState<string | null>(null);

  // Deferred mode: load existing profile to know which phases to skip
  const [deferredState, setDeferredState] = useState<{
    loaded: boolean;
    phasesToSkip: number[];
    existingProfile: Record<string, string | null> | null;
  }>({ loaded: !deferred, phasesToSkip: [], existingProfile: null });

  useEffect(() => {
    if (!deferred) return;
    let cancelled = false;
    async function loadProfile() {
      try {
        const res = await fetch('/api/profile');
        if (!res.ok) {
          if (!cancelled) setDeferredState({ loaded: true, phasesToSkip: [], existingProfile: null });
          return;
        }
        const p = await res.json();
        if (cancelled) return;
        const skip: number[] = [];
        if (p.goal && p.goal !== 'exploring' && p.deadline !== null && p.deadline !== undefined && p.deadline !== '') skip.push(0);
        if (p.overall_level && p.overall_level !== 'beginner') skip.push(1);
        if (p.daily_availability && p.daily_availability !== '1 hour') skip.push(3);
        setDeferredState({ loaded: true, phasesToSkip: skip, existingProfile: p });
      } catch {
        if (!cancelled) setDeferredState({ loaded: true, phasesToSkip: [], existingProfile: null });
      }
    }
    loadProfile();
    return () => { cancelled = true; };
  }, [deferred]);

  const step = done ? 4 : Math.min(3, Math.max(0, apiMsgs.filter(m => m.role === 'user').length - 1));
  const bodyRef  = useRef<HTMLDivElement>(null);
  const textaRef = useRef<HTMLTextAreaElement>(null);
  const started  = useRef(false);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread, busy, done]);

  // Kick off conversation — wait for deferred profile load if needed
  useEffect(() => {
    if (!deferredState.loaded) return;
    if (started.current) return;
    started.current = true;

    if (deferred && deferredState.phasesToSkip.length > 0) {
      const existing = deferredState.existingProfile;
      const parts: string[] = [];
      if (existing?.goal && existing.goal !== 'exploring') parts.push(`goal: ${existing.goal}`);
      if (existing?.deadline) parts.push(`deadline: ${existing.deadline}`);
      if (existing?.overall_level && existing.overall_level !== 'beginner') parts.push(`level: ${existing.overall_level}`);
      if (existing?.daily_availability && existing.daily_availability !== '1 hour') parts.push(`availability: ${existing.daily_availability}`);
      const contextMsg = parts.length > 0
        ? `hi, I'm completing my profile. I already have: ${parts.join(', ')}. Please only ask about what's missing.`
        : 'hi';
      callAgent([{ role: 'user', content: contextMsg }], []);
    } else {
      callAgent([{ role: 'user', content: 'hi' }], []);
    }
  }, [deferredState.loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const extractPartialProfile = useCallback((): Record<string, string> | undefined => {
    const userMsgs = apiMsgs.filter(m => m.role === 'user').slice(1);
    if (userMsgs.length === 0) return undefined;
    const partial: Record<string, string> = {};
    if (userMsgs.length >= 1 && userMsgs[0].content) partial.goal = userMsgs[0].content;
    if (userMsgs.length >= 2 && userMsgs[1].content) partial.overall_level = userMsgs[1].content;
    if (userMsgs.length >= 4 && userMsgs[3].content) partial.daily_availability = userMsgs[3].content;
    return Object.keys(partial).length > 0 ? partial : undefined;
  }, [apiMsgs]);

  const handleSkipConfirm = useCallback(async () => {
    setSkipLoading(true);
    setSkipError(null);
    try {
      const res = await fetch('/api/onboarding/skip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partialProfile: extractPartialProfile() }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setSkipError(data.error || 'Failed to skip onboarding — please try again.');
        setSkipLoading(false);
        return;
      }
      onFinish('exploring');
    } catch {
      setSkipError('Connection failed — please check your network and try again.');
      setSkipLoading(false);
    }
  }, [extractPartialProfile, onFinish]);

  const handleSkipCancel = useCallback(() => {
    if (skipLoading) return;
    setShowSkipDialog(false);
    setSkipError(null);
  }, [skipLoading]);

  const attemptSave = async (p: CompletedProfile) => {
    setSaveFailed(false);
    const endpoint = deferred ? '/api/onboarding/complete-deferred' : '/api/onboarding/complete';
    const res = await fetch(endpoint, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(p),
    }).catch(() => null);
    if (!res?.ok) {
      setSaveFailed(true);
      return;
    }
    setSaveFailed(false);
    if (deferred) {
      setTimeout(() => onFinish(p.goal || 'exploring'), 600);
    } else {
      setTimeout(() => setDone(true), 400);
    }
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

  // Show loading spinner while deferred profile loads
  if (deferred && !deferredState.loaded) {
    return (
      <div className="onb">
        <div className="onb-top"><Brand /></div>
        <div className="onb-stage" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typing />
        </div>
      </div>
    );
  }

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
          <span>{deferred ? 'complete setup' : 'setup'}</span>
          <div className="onb-steps">
            {[0,1,2,3].map(i => (
              <div key={i} className={`s ${i < step || done ? 'done' : i === step ? 'curr' : ''}`} />
            ))}
          </div>
        </div>
        {deferred && onAbandon ? (
          <button className="btn btn-ghost btn-sm" title="Back to Settings" onClick={onAbandon}>
            ← Settings
          </button>
        ) : (
          <>
            <SkipButton onSkip={() => setShowSkipDialog(true)} disabled={busy && thread.length === 0} />
            <button className="icon-btn" title="Sign out" onClick={() => signOut({ redirectUrl: '/sign-in' })}>
              <Icon name="logout" />
            </button>
          </>
        )}
      </div>

      {!deferred && (
        <SkipConfirmationDialog
          open={showSkipDialog}
          onConfirm={handleSkipConfirm}
          onCancel={handleSkipCancel}
          loading={skipLoading}
          error={skipError}
        />
      )}

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
const _LEVEL_ORDER = ['beginner', 'intermediate', 'advanced', 'expert'];

export function SessionEnd({ onFollow, onBack, title, summary, levelFrom, levelTo }: {
  onFollow: () => void;
  onBack: () => void;
  title?: string;
  summary?: string;
  levelFrom?: string | null;
  levelTo?: string | null;
}) {
  const displayTitle = title || 'Session ended';
  const changed = !!levelFrom && !!levelTo && levelFrom !== levelTo;
  const up = changed && _LEVEL_ORDER.indexOf(levelTo!) > _LEVEL_ORDER.indexOf(levelFrom!);
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">{displayTitle}</div><div className="ph-sub">session ended · saved</div></div>
        <div className="ph-right"><span className="pill ok"><span className="ind" /> session saved</span></div>
      </div>
      <div className="se-body">
        <div className="se-inner">
          <div className="se-top">
            <div className="label">Session summary</div>
            <h2 className="title-lg">{displayTitle}</h2>
            <div className="meta">session ended</div>
            {changed && (
              <div className={`level-tag ${up ? 'up' : 'down'}`}>
                {up ? '▲ Leveled up' : '▼ Level adjusted'}: {levelFrom} → {levelTo}
              </div>
            )}
          </div>
          <div className="se-summary">
            <div className="label">Summary</div>
            <div className="body">
              {summary || 'Session saved. Your skill graph has been updated based on this conversation.'}
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

// ---------- Data source upload ------------------------------
// Native file input → POST /api/ingest (validates/stores/extracts server-side).
// Server accepts PDF + CSV (résumé / LeetCode), 50MB max. The extracted chunks
// are read back into the mentor context by context_assembler (issue #4).
function DataSourceUpload() {
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const [msg, setMsg] = useState('');

  const onPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus('uploading');
    setMsg(file.name);
    try {
      const fd = new FormData();
      fd.append('files', file);
      const res = await fetch('/api/ingest', { method: 'POST', body: fd });
      if (!res.ok) {
        setStatus('error');
        setMsg(res.status === 400 ? 'Unsupported file — use a PDF or CSV.' : 'Upload failed — try again.');
      } else {
        setStatus('done');
        setMsg(`${file.name} uploaded — your mentor will use it shortly.`);
      }
    } catch {
      setStatus('error');
      setMsg('Connection error — try again.');
    } finally {
      e.target.value = ''; // allow re-selecting the same file
    }
  };

  return (
    <div style={{ padding: '8px 0' }}>
      <label className="btn btn-sm btn-ghost" style={{ cursor: 'pointer' }}>
        {status === 'uploading' ? 'Uploading…' : 'Upload résumé (PDF) or LeetCode (CSV)'}
        <input type="file" accept=".pdf,.csv" onChange={onPick} disabled={status === 'uploading'} style={{ display: 'none' }} />
      </label>
      {status !== 'idle' && status !== 'uploading' && (
        <div style={{ color: status === 'error' ? 'var(--danger)' : 'var(--muted)', fontSize: 12, marginTop: 6 }}>
          {msg}
        </div>
      )}
    </div>
  );
}

// ---------- Settings ----------------------------------------
export function Settings({ profile, onReset, onSaved, onStartDeferredOnboarding }: {
  profile: CoreProfile | null;
  onReset: () => void;
  onSaved: () => void;
  onStartDeferredOnboarding?: () => void;
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

          {profile?.profile_status === 'skipped' && onStartDeferredOnboarding && (
            <CompleteSetupSection onStartSetup={onStartDeferredOnboarding} />
          )}

          <div className="set-section">
            <div className="set-label">Data sources</div>
            <DataSourceUpload />
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

