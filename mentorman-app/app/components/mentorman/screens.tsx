'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useClerk } from '@clerk/nextjs';
import { useRouter } from 'next/navigation';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { SEEDS, EVAL_SEED, EVAL_DONE_EXTRA, MODES, mentorSystemPrompt, type MessageItem, type ToneId } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';
import { CompleteSetupSection } from './CompleteSetupSection';
import { SkipButton } from './SkipButton';
import { SkipConfirmationDialog } from './SkipConfirmationDialog';

// ---------- Onboarding (conversational AI agent) ----------------

type ApiMsg = { role: 'user' | 'assistant'; content: string };
type CompletedProfile = { goal: string; deadline: string; overall_level: string; daily_availability: string };

export interface OnboardingProps {
  onFinish: (goal: string) => void;
  userName?: string;
  /** When true, runs in deferred mode — skips already-completed phases */
  deferred?: boolean;
  /** Called when user abandons deferred onboarding (navigates away without completing) */
  onAbandon?: () => void;
}

export function Onboarding({ onFinish, userName, deferred = false, onAbandon }: OnboardingProps) {
  const { signOut } = useClerk();
  const router = useRouter();
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

  // Skip onboarding state
  const [showSkipDialog, setShowSkipDialog] = useState(false);
  const [skipLoading,    setSkipLoading]    = useState(false);
  const [skipError,      setSkipError]      = useState<string | null>(null);

  // Extract partial profile data from the conversation state (assistant messages may contain parsed fields)
  const extractPartialProfile = useCallback((): Record<string, string> | undefined => {
    // Look through assistant messages for any structured data that the LLM may have extracted
    // The onboarding LLM collects: goal, deadline, overall_level, daily_availability
    // We can infer partial data from the number of user responses (phases completed)
    const userMsgs = apiMsgs.filter(m => m.role === 'user').slice(1); // skip initial "hi"
    if (userMsgs.length === 0) return undefined;

    const partial: Record<string, string> = {};
    // Phase 0 collects goal + deadline from the first user response
    if (userMsgs.length >= 1 && userMsgs[0].content) {
      partial.goal = userMsgs[0].content;
    }
    // Phase 1 collects overall_level
    if (userMsgs.length >= 2 && userMsgs[1].content) {
      partial.overall_level = userMsgs[1].content;
    }
    // Phase 2 is file upload — no profile field extracted
    // Phase 3 collects daily_availability
    if (userMsgs.length >= 4 && userMsgs[3].content) {
      partial.daily_availability = userMsgs[3].content;
    }

    return Object.keys(partial).length > 0 ? partial : undefined;
  }, [apiMsgs]);

  // Handle skip confirmation — call POST /api/onboarding/skip
  const handleSkipConfirm = useCallback(async () => {
    setSkipLoading(true);
    setSkipError(null);

    try {
      const partialProfile = extractPartialProfile();
      const res = await fetch('/api/onboarding/skip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partialProfile }),
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        setSkipError(data.error || 'Failed to skip onboarding — please try again.');
        setSkipLoading(false);
        return;
      }

      // Requirement 2.3: Redirect to Chat Interface within 1 second
      // Requirement 2.6: Terminate onboarding conversation without sending further messages
      if (data.sessionId) {
        router.push(`/session/${data.sessionId}`);
      } else {
        onFinish('exploring');
      }
    } catch {
      setSkipError('Connection failed — please check your network and try again.');
      setSkipLoading(false);
    }
  }, [extractPartialProfile, router, onFinish]);

  // Handle skip cancel — dismiss dialog, clear error
  const handleSkipCancel = useCallback(() => {
    if (skipLoading) return; // Don't allow cancel while API call in progress
    setShowSkipDialog(false);
    setSkipError(null);
  }, [skipLoading]);

  // Deferred mode: fetch existing profile to determine which phases to skip
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
        // Phase 0: skip if goal ≠ "exploring" AND deadline ≠ null
        if (p.goal && p.goal !== 'exploring' && p.deadline !== null && p.deadline !== undefined && p.deadline !== '') {
          skip.push(0);
        }
        // Phase 1: skip if overall_level ≠ "beginner"
        if (p.overall_level && p.overall_level !== 'beginner') {
          skip.push(1);
        }
        // Phase 2: File Upload — always included in deferred mode
        // Phase 3: skip if daily_availability ≠ "1 hour"
        if (p.daily_availability && p.daily_availability !== '1 hour') {
          skip.push(3);
        }

        setDeferredState({ loaded: true, phasesToSkip: skip, existingProfile: p });
      } catch {
        if (!cancelled) setDeferredState({ loaded: true, phasesToSkip: [], existingProfile: null });
      }
    }
    loadProfile();
    return () => { cancelled = true; };
  }, [deferred]);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread, busy, done]);

  // Kick off conversation on mount — send a silent "hi" to get the first question
  // In deferred mode, wait until profile is loaded and include context about skipped phases
  useEffect(() => {
    if (started.current) return;
    if (!deferredState.loaded) return;
    started.current = true;

    if (deferred && deferredState.phasesToSkip.length > 0) {
      // Build context message that tells the LLM which info we already have
      const existing = deferredState.existingProfile;
      const contextParts: string[] = [];
      if (existing?.goal && existing.goal !== 'exploring') contextParts.push(`goal: ${existing.goal}`);
      if (existing?.deadline) contextParts.push(`deadline: ${existing.deadline}`);
      if (existing?.overall_level && existing.overall_level !== 'beginner') contextParts.push(`level: ${existing.overall_level}`);
      if (existing?.daily_availability && existing.daily_availability !== '1 hour') contextParts.push(`availability: ${existing.daily_availability}`);

      const contextMsg = contextParts.length > 0
        ? `hi, I'm completing my profile. I already have: ${contextParts.join(', ')}. Please only ask about what's missing.`
        : 'hi';

      callAgent([{ role: 'user', content: contextMsg }], []);
    } else {
      callAgent([{ role: 'user', content: 'hi' }], []);
    }
  }, [deferredState.loaded]); // eslint-disable-line react-hooks/exhaustive-deps

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
      // Requirement 5.4: redirect to Chat Interface within 1 second
      setTimeout(() => onFinish(p.goal), 600);
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

  // Don't render until deferred profile state is loaded
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
          <button
            className="btn btn-ghost btn-sm"
            title="Back to Settings"
            onClick={onAbandon}
          >
            ← Settings
          </button>
        ) : (
          <>
            <SkipButton
              onSkip={() => setShowSkipDialog(true)}
              disabled={busy && thread.length === 0}
            />
            <button
              className="icon-btn"
              title="Sign out"
              onClick={() => signOut({ redirectUrl: '/sign-in' })}
            >
              <Icon name="logout" />
            </button>
          </>
        )}
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

      {/* Skip Confirmation Dialog — only in non-deferred mode */}
      {!deferred && (
        <SkipConfirmationDialog
          open={showSkipDialog}
          onConfirm={handleSkipConfirm}
          onCancel={handleSkipCancel}
          loading={skipLoading}
          error={skipError}
        />
      )}
    </div>
  );
}

// ---------- Evaluation panel --------------------------------
export function EvalPanel({ onComplete }: { onComplete: () => void }) {
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [phase, setPhase] = useState<'mid' | 'done'>('mid');
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMsgs([]); setPhase('mid');
    const timers: ReturnType<typeof setTimeout>[] = [];
    EVAL_SEED.forEach((m, i) => timers.push(setTimeout(() => setMsgs(p => [...p, { ...m, _id: 'e' + i }]), 160 + i * 520)));
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, phase]);

  const finish = () => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    EVAL_DONE_EXTRA.forEach((m, i) => timers.push(setTimeout(() => setMsgs(p => [...p, { ...m, _id: 'ed' + i }]), i * 520)));
    setTimeout(() => setPhase('done'), EVAL_DONE_EXTRA.length * 520 + 200);
  };

  const answered = phase === 'done' ? 5 : 2;
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">Evaluation — Graphs · week 3</div>
          <div className="ph-sub">structured Q → verdict → score</div>
        </div>
        <div className="ph-right">
          <span className="eval-progress">
            Q<span className="qn">{phase === 'done' ? 5 : 2}</span>of 5
            <span className="eval-dots">
              {[0,1,2,3,4].map(i => (
                <span key={i} className={`d ${i < answered ? 'done' : i === answered ? 'curr' : ''}`} />
              ))}
            </span>
          </span>
          <span className="pill ok"><span className="ind" /> {phase === 'done' ? '3 / 5' : '1 / 1'} correct</span>
        </div>
      </div>

      <div className="chat-body" ref={bodyRef}>
        <div className="chat-inner">
          {msgs.map((m, i) =>
            m.who === 'verdict'
              ? <VerdictMsg key={m._id || i} item={m as any} />
              : <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />
          )}
        </div>
      </div>

      {phase === 'mid' ? (
        <div className="composer">
          <div className="eval-flag"><span className="dot" /> Evaluation mode — your answer is graded</div>
          <div className="composer-inner">
            <div className="composer-box">
              <textarea rows={1} placeholder="Type your answer to Q3…" />
              <div className="composer-tools">
                <button className="tool-btn">+</button>
                <button className="tool-btn">{'</>'}</button>
                <div className="spacer" />
                <button className="btn btn-accent btn-sm" onClick={finish}>Submit &amp; finish demo</button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="composer">
          <div className="summary-card">
            <div className="sc-h"><span className="check"><Icon name="check" size={12} /></span> Evaluation complete</div>
            <div className="summary-score"><div className="big">3 / 5</div><div className="lbl">graphs · week 3</div></div>
            <div className="summary-cols">
              <div className="summary-col">
                <div className="colhead">Strong areas</div>
                <div className="area-tags">
                  <span className="area-tag strong">BFS recall</span>
                  <span className="area-tag strong">DFS basics</span>
                  <span className="area-tag strong">0-1 BFS reasoning</span>
                </div>
              </div>
              <div className="summary-col">
                <div className="colhead">Weak areas</div>
                <div className="area-tags">
                  <span className="area-tag warn">portal / cost-0 edges</span>
                  <span className="area-tag warn">Dijkstra heap</span>
                </div>
              </div>
            </div>
            <div className="summary-update">Skill graph updated · <b>graphs → medium+</b> · +13%</div>
            <button className="btn btn-accent" style={{ width: '100%', height: 40 }} onClick={onComplete}>
              Start Topic session on weak areas <Icon name="arrowR" size={15} />
            </button>
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

          {/* Complete Setup section — shown only for skipped profiles */}
          {profile?.profile_status === 'skipped' && onStartDeferredOnboarding && (
            <CompleteSetupSection onStartSetup={onStartDeferredOnboarding} />
          )}

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

// ---------- Mobile chat (phone frame) -----------------------
export function MobileChat({ onClose, tone }: { onClose: () => void; tone: ToneId }) {
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [val, setVal] = useState('');
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const seed = SEEDS.s1.slice(0, 3);
    const timers: ReturnType<typeof setTimeout>[] = [];
    seed.forEach((m, i) => timers.push(setTimeout(() => setMsgs(p => [...p, { ...m, _id: 'p' + i }]), 200 + i * 520)));
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  const send = async () => {
    const t = val.trim();
    if (!t || busy) return;
    setVal('');
    const um: MessageItem = { who: 'user', text: t, _id: 'u' + Date.now() };
    setMsgs(p => [...p, um]);
    setBusy(true);
    try {
      const history = [...msgs, um].map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
      const res = await fetch('/api/mentor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system: mentorSystemPrompt('topic', tone, 'Graphs — BFS/DFS warmups'), messages: history }),
      });
      const { text: reply } = await res.json();
      setMsgs(p => [...p, { who: 'mentor', text: (reply || '').trim() || "Say more — where exactly does it break?", _id: 'm' + Date.now() }]);
    } catch {
      setMsgs(p => [...p, { who: 'mentor', text: "Lost my notes for a sec — try again?", _id: 'm' + Date.now() }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mobile-overlay" onClick={onClose}>
      <div className="phone" onClick={e => e.stopPropagation()}>
        <div className="notch" />
        <div className="phone-status"><span>9:41</span><span>MentorMan</span><span>▮▮▮ 100%</span></div>
        <div className="phone-head">
          <div className="back" onClick={onClose}><Icon name="back" /></div>
          <div><div className="pt">Graphs — BFS/DFS</div><div className="ps">● topic mode · active</div></div>
        </div>
        <div className="phone-body" ref={bodyRef}>
          {msgs.map((m, i) => <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />)}
          {busy && <Typing />}
        </div>
        <div className="phone-modes">
          {MODES.map(m => <div key={m.id} className={`phone-mode ${m.id === 'topic' ? 'active' : ''}`}>{m.label}</div>)}
        </div>
        <div className="phone-composer">
          <input className="pc-input" value={val} placeholder="Reply…" onChange={e => setVal(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter') send(); }} />
          <button className="send-btn" onClick={send} disabled={busy || !val.trim()}><Icon name="send" /></button>
        </div>
        <button className="icon-btn phone-close" style={{ background: 'var(--card)', border: '1px solid var(--border)' }} onClick={onClose}><Icon name="x" /></button>
      </div>
    </div>
  );
}
