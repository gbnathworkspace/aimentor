'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../auth/useAuth';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { type MessageItem } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';
import { SkipButton } from './SkipButton';
import { SkipConfirmationDialog } from './SkipConfirmationDialog';
import { CompleteSetupSection } from './CompleteSetupSection';
import { MentorQuestionCard, QuickReplyOptions, type QuickReplyOption } from './QuestionCard';

// ---------- Onboarding (conversational AI agent) ----------------

type ApiMsg = { role: 'user' | 'assistant'; content: string };
type CompletedProfile = {
  learning_context: string;
  learning_context_label: string | null;
  focus_areas: string[];
  explanation_style: string;
  challenge_tolerance: string;
  feedback_tone: string;
};

export interface OnboardingProps {
  onFinish: (goal: string) => void;
  userName?: string;
  deferred?: boolean;
  onAbandon?: () => void;
}

export function Onboarding({ onFinish, userName, deferred = false, onAbandon }: OnboardingProps) {
  const { logout } = useAuth();
  const [apiMsgs,    setApiMsgs]    = useState<ApiMsg[]>([]);
  const [thread,     setThread]     = useState<MessageItem[]>([]);
  const [busy,       setBusy]       = useState(false);
  const [done,       setDone]       = useState(false);
  const [profile,    setProfile]    = useState<CompletedProfile | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const [input,       setInput]       = useState('');
  const [suggestions, setSuggestions] = useState<QuickReplyOption[]>([]);

  // Skip state
  const [showSkipDialog, setShowSkipDialog] = useState(false);
  const [skipLoading,    setSkipLoading]    = useState(false);
  const [skipError,      setSkipError]      = useState<string | null>(null);

  // Deferred mode: load existing profile so the agent skips what's already known
  const [deferredState, setDeferredState] = useState<{
    loaded: boolean;
    knownParts: string[];
  }>({ loaded: !deferred, knownParts: [] });

  useEffect(() => {
    if (!deferred) return;
    let cancelled = false;
    async function loadProfile() {
      try {
        const res = await fetch('/api/profile');
        if (!res.ok) {
          if (!cancelled) setDeferredState({ loaded: true, knownParts: [] });
          return;
        }
        const p = await res.json();
        if (cancelled) return;
        const parts: string[] = [];
        if (p.learning_context) parts.push(`learning context: ${p.learning_context}`);
        if (p.learning_context_detail?.label) parts.push(`situation: ${p.learning_context_detail.label}`);
        if (p.focus_areas?.length) parts.push(`focus areas: ${p.focus_areas.join(', ')}`);
        if (p.explanation_style) parts.push(`explanation style: ${p.explanation_style}`);
        if (p.challenge_tolerance) parts.push(`challenge tolerance: ${p.challenge_tolerance}`);
        if (p.feedback_tone) parts.push(`feedback tone: ${p.feedback_tone}`);
        setDeferredState({ loaded: true, knownParts: parts });
      } catch {
        if (!cancelled) setDeferredState({ loaded: true, knownParts: [] });
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

    if (deferred && deferredState.knownParts.length > 0) {
      const contextMsg = `hi, I'm completing my profile. I already have: ${deferredState.knownParts.join(', ')}. Please only ask about what's missing.`;
      callAgent([{ role: 'user', content: contextMsg }], []);
    } else {
      callAgent([{ role: 'user', content: 'hi' }], []);
    }
  }, [deferredState.loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ponytail: no per-field partial-profile guess on skip — with the new prompt
  // asking things in whatever order the model chooses, and learning_context now
  // a strict enum, guessing a field from raw message text risks writing an
  // invalid value that 500s on the next profile read. Backend defaults cover it.
  const handleSkipConfirm = useCallback(async () => {
    setSkipLoading(true);
    setSkipError(null);
    try {
      const res = await fetch('/api/onboarding/skip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
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
  }, [onFinish]);

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
      setTimeout(() => onFinish(p.focus_areas?.[0] || p.learning_context_label || 'exploring'), 600);
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
            <button className="icon-btn" title="Sign out" onClick={() => logout()}>
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
          {thread.map(m => (
            m.who === 'mentor'
              ? <MentorQuestionCard key={m._id} text={m.text} />
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
                <div className="setup-line"><span className="k">context</span><span className="v">{profile.learning_context_label || profile.learning_context}</span></div>
                <div className="setup-line"><span className="k">focus</span><span className="v">{profile.focus_areas.join(', ') || '—'}</span></div>
                <div className="setup-line"><span className="k">style</span><span className="v">{profile.explanation_style} · {profile.challenge_tolerance} · {profile.feedback_tone}</span></div>
              </div>
              <button
                className="btn btn-accent" style={{ width: '100%', height: 42 }}
                onClick={() => onFinish(profile.focus_areas[0] || profile.learning_context_label || 'exploring')}
              >
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
              <QuickReplyOptions
                options={suggestions}
                onSelect={sendText}
                onTypeOwn={() => { setSuggestions([]); textaRef.current?.focus(); }}
                onClose={() => setSuggestions([])}
              />
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
  const [editName, setEditName] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const [contextVal, setContextVal] = useState(profile?.learning_context ?? 'self_directed');
  const [labelVal, setLabelVal] = useState(profile?.learning_context_detail?.label ?? '');
  const [focusVal, setFocusVal] = useState((profile?.focus_areas ?? []).join(', '));
  const [explanationVal, setExplanationVal] = useState(profile?.explanation_style ?? 'hint-first');
  const [challengeVal, setChallengeVal] = useState(profile?.challenge_tolerance ?? 'medium');
  const [toneVal, setToneVal] = useState(profile?.feedback_tone ?? 'encouraging');
  const [nameVal, setNameVal] = useState(profile?.name ?? '');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  // Sync form values when profile loads / changes
  useEffect(() => {
    setContextVal(profile?.learning_context ?? 'self_directed');
    setLabelVal(profile?.learning_context_detail?.label ?? '');
    setFocusVal((profile?.focus_areas ?? []).join(', '));
    setExplanationVal(profile?.explanation_style ?? 'hint-first');
    setChallengeVal(profile?.challenge_tolerance ?? 'medium');
    setToneVal(profile?.feedback_tone ?? 'encouraging');
    setNameVal(profile?.name ?? '');
  }, [profile]);

  const save = async (field: Record<string, unknown>): Promise<boolean> => {
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

  const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

  const onAvatarPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    setAvatarError(null);
    if (!file.type.startsWith('image/')) {
      setAvatarError('Please choose an image file.');
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setAvatarError('Image is too large (max 2MB).');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUri = reader.result as string;
      save({ avatar: dataUri }).then(ok => { if (!ok) setAvatarError('Upload failed — please try again.'); });
    };
    reader.onerror = () => setAvatarError('Could not read that file — please try again.');
    reader.readAsDataURL(file);
  };

  const removeAvatar = () => { save({ avatar: '' }); };

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

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">Profile &amp; Settings</div><div className="ph-sub">context · focus · style</div></div>
      </div>
      <div className="set-body">
        <div className="set-inner">

          {saveError && (
            <div style={{ fontSize: 12, color: '#f87171', padding: '8px 12px', background: 'rgba(248,113,113,0.08)', borderRadius: 6, marginBottom: 8 }}>
              {saveError}
            </div>
          )}

          <div className="set-section">
            <div className="set-label">Profile</div>

            <div className="set-row" style={{ gap: 16 }}>
              <div style={{ position: 'relative', flexShrink: 0 }}>
                {profile?.avatar ? (
                  <img src={profile.avatar} alt="Profile" style={{ width: 56, height: 56, borderRadius: '50%', objectFit: 'cover' }} />
                ) : (
                  <div className="avatar" style={{ width: 56, height: 56, fontSize: 22 }}>
                    {(profile?.name || profile?.email || 'Y')[0]?.toUpperCase()}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-sm btn-ghost" disabled={saving} onClick={() => avatarInputRef.current?.click()}>
                    {profile?.avatar ? 'Change photo' : 'Upload photo'}
                  </button>
                  {profile?.avatar && (
                    <button className="btn btn-sm btn-ghost" disabled={saving} onClick={removeAvatar}>Remove</button>
                  )}
                </div>
                <input ref={avatarInputRef} type="file" accept="image/*" onChange={onAvatarPick} style={{ display: 'none' }} />
                {avatarError && <div style={{ fontSize: 11, color: 'var(--danger)' }}>{avatarError}</div>}
              </div>
            </div>

            <div className="set-row">
              <div className="k">Name</div>
              {editName ? (
                <div style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    className="num-input" style={{ flex: 1 }}
                    value={nameVal}
                    onChange={e => setNameVal(e.target.value)}
                  />
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditName(false); setNameVal(profile?.name ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { if (await save({ name: nameVal })) setEditName(false); }}>Save</button>
                </div>
              ) : (
                <>
                  <div className="v">{profile?.name || '—'}</div>
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditName(true)}>Edit</button>
                </>
              )}
            </div>
          </div>

          <div className="set-section">
            <div className="set-label">Learning context</div>

            <div className="set-row">
              <div className="k">Context</div>
              <select className="num-input" value={contextVal} onChange={e => setContextVal(e.target.value)}>
                <option value="job_interview">Job interview</option>
                <option value="high_stakes_exam">High-stakes exam</option>
                <option value="competitive_test">Competitive test</option>
                <option value="self_directed">Self-directed</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="set-row">
              <div className="k">Situation</div>
              <input
                className="num-input" style={{ flex: 1 }}
                value={labelVal}
                placeholder="e.g. senior backend roles, 20 LPA target"
                onChange={e => setLabelVal(e.target.value)}
              />
            </div>

            <button
              className="btn btn-sm btn-primary" style={{ marginTop: 6, alignSelf: 'flex-start' }}
              disabled={saving || (
                contextVal === (profile?.learning_context ?? 'self_directed') &&
                labelVal === (profile?.learning_context_detail?.label ?? '')
              )}
              onClick={() => save({
                learning_context: contextVal,
                learning_context_detail: { learning_context: contextVal, label: labelVal || null, structured: {} },
              })}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>

          <div className="set-section">
            <div className="set-label">Focus areas</div>
            <div className="set-row">
              <input
                className="num-input" style={{ flex: 1 }}
                value={focusVal}
                placeholder="e.g. System Design, DSA, Behavioral"
                onChange={e => setFocusVal(e.target.value)}
              />
              <button
                className="btn btn-sm btn-primary"
                disabled={saving || focusVal === (profile?.focus_areas ?? []).join(', ')}
                onClick={() => save({ focus_areas: focusVal.split(',').map(s => s.trim()).filter(Boolean) })}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>

          {profile?.profile_status === 'skipped' && onStartDeferredOnboarding && (
            <CompleteSetupSection onStartSetup={onStartDeferredOnboarding} />
          )}

          <div className="set-section">
            <div className="set-label">How should the mentor teach you?</div>
            <div style={{ color: 'var(--muted)', fontSize: 12, padding: '4px 0 8px' }}>
              These preferences apply in every reply, across all topics and modes.
            </div>

            <div className="set-row">
              <div className="k">Explanation style</div>
              <select className="num-input" value={explanationVal} onChange={e => setExplanationVal(e.target.value)}>
                <option value="hint-first">Hints first</option>
                <option value="answer-first">Answer first</option>
              </select>
            </div>
            <div className="set-row">
              <div className="k">Challenge tolerance</div>
              <select className="num-input" value={challengeVal} onChange={e => setChallengeVal(e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            <div className="set-row">
              <div className="k">Feedback tone</div>
              <select className="num-input" value={toneVal} onChange={e => setToneVal(e.target.value)}>
                <option value="direct">Direct</option>
                <option value="encouraging">Encouraging</option>
              </select>
            </div>

            <button
              className="btn btn-sm btn-primary" style={{ marginTop: 6, alignSelf: 'flex-start' }}
              disabled={saving || (
                explanationVal === (profile?.explanation_style ?? 'hint-first') &&
                challengeVal === (profile?.challenge_tolerance ?? 'medium') &&
                toneVal === (profile?.feedback_tone ?? 'encouraging')
              )}
              onClick={() => save({ explanation_style: explanationVal, challenge_tolerance: challengeVal, feedback_tone: toneVal })}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>

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
                  <button className="danger-btn" onClick={() => setConfirmReset(true)}>Reset profile and skill graph</button>
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

// ---------- Admin: user management ---------------------------
interface AdminUser {
  user_id: string;
  email?: string;
  auth_method?: string;
  is_active?: boolean;
  is_admin?: boolean;
  created_at?: string;
}

const PAGE_SIZE = 20;

export function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/admin/users?page=${page}&page_size=${PAGE_SIZE}`)
      .then(r => {
        if (r.status === 403) throw new Error('Admins only — you don’t have access to this page.');
        if (!r.ok) throw new Error('Failed to load users.');
        return r.json();
      })
      .then(data => { setUsers(data.users ?? []); setTotal(data.total ?? 0); })
      .catch(e => setError(e.message || 'Failed to load users.'))
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { load(); }, [load]);

  const toggleActive = async (u: AdminUser) => {
    setPendingId(u.user_id);
    try {
      const action = u.is_active ? 'deactivate' : 'activate';
      const res = await fetch(`/api/admin/users/${u.user_id}/${action}`, { method: 'POST' });
      if (res.ok) setUsers(prev => prev.map(x => x.user_id === u.user_id ? { ...x, is_active: !u.is_active } : x));
    } finally {
      setPendingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">Users</div><div className="ph-sub">{total} total</div></div>
      </div>
      <div className="set-body">
        <div className="set-inner">
          {error ? (
            <div style={{ fontSize: 12, color: '#f87171', padding: '8px 12px', background: 'rgba(248,113,113,0.08)', borderRadius: 6 }}>
              {error}
            </div>
          ) : loading ? (
            <div style={{ color: 'var(--muted)', fontSize: 13, padding: 12 }}>Loading users…</div>
          ) : (
            <div className="set-section">
              {users.map(u => (
                <div key={u.user_id} className="set-row" style={{ alignItems: 'center' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="v" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {u.email || u.user_id}
                      {u.is_admin && <span className="pill info">admin</span>}
                      <span className={`pill ${u.is_active ? 'ok' : 'warn'}`}><span className="ind" />{u.is_active ? 'active' : 'inactive'}</span>
                    </div>
                  </div>
                  <button
                    className={u.is_active ? 'danger-btn' : 'btn btn-sm btn-primary'}
                    disabled={pendingId === u.user_id}
                    onClick={() => toggleActive(u)}
                  >
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              ))}
              {users.length === 0 && (
                <div style={{ color: 'var(--muted)', fontSize: 13, padding: 12 }}>No users found.</div>
              )}
            </div>
          )}

          {!error && totalPages > 1 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', padding: '12px 0' }}>
              <button className="btn btn-sm btn-ghost" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</button>
              <span style={{ fontSize: 12, color: 'var(--muted)', alignSelf: 'center' }}>{page} / {totalPages}</span>
              <button className="btn btn-sm btn-ghost" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

