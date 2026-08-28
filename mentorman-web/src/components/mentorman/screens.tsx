'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../auth/useAuth';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { type MessageItem } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';
import { SkipButton } from './SkipButton';
import { SkipConfirmationDialog } from './SkipConfirmationDialog';

// ponytail: no backend classifier for fact quality — this is a keyword/length
// heuristic, not a real vagueness judgment. Swap for a real signal (LLM
// classification, or a flag the profiling agent sets) if it needs to be sharp.
const VAGUE_WORDS = /\b(sometimes|kind of|sort of|maybe|a bit|a little|stuff|things|somewhat|generally|usually|often|whatever|etc)\b/i;
function isVagueFact(text: string): boolean {
  const words = text.trim().split(/\s+/).filter(Boolean);
  return words.length <= 4 || VAGUE_WORDS.test(text);
}

// `topicReason` is the LLM's verdict (see fact_quality.py via the
// /api/profile/situations/quality fetch below) for facts that read like a
// topic/skill name instead of something true about the user — undefined
// while that judgment hasn't loaded yet or the entry passed it.
function factWarning(text: string, topicReason?: string): string | null {
  if (isVagueFact(text)) return 'Too vague to act on — try naming specifics.';
  if (topicReason) return topicReason;
  return null;
}

import { MentorQuestionCard, QuickReplyOptions, type QuickReplyOption } from './QuestionCard';
import { AttachButton } from './chat/AttachButton';
import { AttachmentPreview } from './chat/AttachmentPreview';
import { DocumentUploadFlow } from './chat/DocumentUploadFlow';
import { useAttachedFiles } from '@/lib/chat-upload/useAttachedFiles';
import type { UseDocumentUploadFlowReturn } from '@/lib/chat-upload/useDocumentUploadFlow';

// ---------- Onboarding (conversational AI agent) ----------------

type ApiMsg = { role: 'user' | 'assistant'; content: string };
type CompletedProfile = {
  learning_context_label: string | null;
  focus_areas: string[];
};

export interface OnboardingProps {
  onFinish: (goal: string) => void;
  userName?: string;
}

export function Onboarding({ onFinish, userName }: OnboardingProps) {
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

  const step = done ? 4 : Math.min(3, Math.max(0, apiMsgs.filter(m => m.role === 'user').length - 1));
  const bodyRef  = useRef<HTMLDivElement>(null);
  const textaRef = useRef<HTMLTextAreaElement>(null);
  const started  = useRef(false);

  // Includes `suggestions` — the options card takes its own space below the
  // thread (not an overlay), so the thread shrinks when it appears; without
  // re-scrolling here, the tail of the last message looks cut off behind it.
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread, busy, done, suggestions]);

  // Kick off conversation
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    callAgent([{ role: 'user', content: 'hi' }], []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ponytail: no per-field partial-profile guess on skip — with the new prompt
  // asking things in whatever order the model chooses, guessing a field from
  // raw message text risks writing something malformed. Backend defaults cover it.
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
        <SkipButton onSkip={() => setShowSkipDialog(true)} disabled={busy && thread.length === 0} />
        <button className="icon-btn" title="Sign out" onClick={() => logout()}>
          <Icon name="logout" />
        </button>
      </div>

      <SkipConfirmationDialog
        open={showSkipDialog}
        onConfirm={handleSkipConfirm}
        onCancel={handleSkipCancel}
        loading={skipLoading}
        error={skipError}
      />

      <div className="onb-stage" ref={bodyRef}>
        <div className="onb-thread">
          {thread.map(m => (
            m.who === 'mentor'
              ? <MentorQuestionCard key={m._id} text={m.text} />
              : <Bubble key={m._id} who={m.who as 'mentor' | 'user'} item={m} />
          ))}
          {busy && <Typing />}

          {!busy && suggestions.length > 0 && (
            <div className="chat-options">
              <QuickReplyOptions
                options={suggestions}
                onSelect={sendText}
                onTypeOwn={() => { setSuggestions([]); textaRef.current?.focus(); }}
                onClose={() => setSuggestions([])}
              />
            </div>
          )}

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
                <div className="setup-line"><span className="k">context</span><span className="v">{profile.learning_context_label || '—'}</span></div>
                <div className="setup-line"><span className="k">facts</span><span className="v">{profile.focus_areas.join(', ') || '—'}</span></div>
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

// ---------- Settings ----------------------------------------
export function Settings({ profile, avatarUrl, onAvatarChanged, onReset, onSaved, onClose }: {
  profile: CoreProfile | null;
  avatarUrl?: string | null;
  onAvatarChanged?: () => void;
  onReset: () => void;
  onSaved: () => void;
  onClose?: () => void;
}) {
  const [tab, setTab] = useState<'profile' | 'memory'>('profile');
  const [memorySubTab, setMemorySubTab] = useState<'knows' | 'data'>('knows');
  const [editName, setEditName] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [wipeText, setWipeText] = useState('');

  // Inline "what you've told it" editor — null id means nothing is being edited.
  const [editingSituation, setEditingSituation] = useState<{ index: number; draft: string } | null>(null);

  const [nameVal, setNameVal] = useState(profile?.name ?? '');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  // Sync form values when profile loads / changes
  useEffect(() => {
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


  const removeStyleNote = (index: number) => save({
    style_notes: (profile?.style_notes ?? []).filter((_, i) => i !== index),
  });

  const exportMemory = () => {
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mentorman-memory.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  // `label` mirrors the first entry of the list — plenty of backend readers
  // still take that single-value field. There's no separate `contexts`
  // field any more — it duplicated this same list with no UI of its own
  // (see l1_scope.extract_situations).
  const saveSituations = (situations: string[]) => save({
    learning_context_detail: {
      label: situations[0] ?? null,
      situations,
    },
  });

  const situations = profile?.learning_context_detail?.situations ?? [];

  // LLM judgment of whether each "Facts About You" entry actually states a
  // fact vs. just names a topic (see app/services/fact_quality.py) — keyed
  // by the joined situations list so it only refetches when that changes,
  // not on every unrelated Settings re-render.
  const [factQuality, setFactQuality] = useState<Record<string, { reason: string; rewrite?: string }>>({});
  const situationsKey = situations.join(' ');
  useEffect(() => {
    if (situations.length === 0) { setFactQuality({}); return; }
    let cancelled = false;
    fetch('/api/profile/situations/quality')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled || !data?.judgments) return;
        const next: Record<string, { reason: string; rewrite?: string }> = {};
        for (const j of data.judgments) {
          if (j.is_fact === false) next[j.text] = { reason: j.reason, rewrite: j.rewrite ?? undefined };
        }
        setFactQuality(next);
      })
      .catch(() => {});
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [situationsKey]);
  const applyFactRewrite = (index: number, rewrite: string) =>
    saveSituations(situations.map((s, i) => (i === index ? rewrite : s)));

  const startEditSituation = (index: number) => setEditingSituation({ index, draft: situations[index] ?? '' });
  const addSituation = () => {
    const next = [...situations, ''];
    setEditingSituation({ index: next.length - 1, draft: '' });
  };
  const commitSituation = () => {
    if (!editingSituation) return;
    const { index, draft } = editingSituation;
    const text = draft.trim();
    const isNew = index >= situations.length;
    if (isNew) {
      if (text) saveSituations([...situations, text]);
    } else if (text) {
      saveSituations(situations.map((s, i) => (i === index ? text : s)));
    } else {
      saveSituations(situations.filter((_, i) => i !== index));
    }
    setEditingSituation(null);
  };
  const removeSituation = (index: number) => saveSituations(situations.filter((_, i) => i !== index));

  const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

  const saveAvatar = async (avatar: string | null): Promise<boolean> => {
    try {
      const res = await fetch('/api/profile/avatar', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ avatar }),
      });
      if (!res.ok) return false;
      onAvatarChanged?.();
      return true;
    } catch {
      return false;
    }
  };

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
      saveAvatar(dataUri).then(ok => { if (!ok) setAvatarError('Upload failed — please try again.'); });
    };
    reader.onerror = () => setAvatarError('Could not read that file — please try again.');
    reader.readAsDataURL(file);
  };

  const removeAvatar = () => { saveAvatar(null); };

  const [resolvingField, setResolvingField] = useState<string | null>(null);
  const resolvePendingChange = async (field: string, action: 'accept' | 'dismiss') => {
    setResolvingField(field);
    try {
      const res = await fetch(`/api/profile/pending-changes/${field}/${action}`, { method: 'POST' });
      if (res.ok) onSaved();
    } finally {
      setResolvingField(null);
    }
  };

  const describePendingChange = (field: string, value: Record<string, unknown>): string => {
    if (field === 'style_note') return `New teaching note: "${value.note}"`;
    if (field === 'situation') return `New fact: "${value.value}"`;
    return field;
  };

  // Collapsed by default so the pending-review queue doesn't visually bleed
  // into the settings fields below it — expand on click, same control closes it.
  const [suggestedOpen, setSuggestedOpen] = useState(false);

  // Direct natural-language memory edit (applies immediately — the user typed
  // it themselves, same trust level as editing a field). See
  // app/services/memory_editor.py, distinct from the inferred pending_changes.
  const [memoryMsg, setMemoryMsg] = useState('');
  const [memoryEditing, setMemoryEditing] = useState(false);
  const [memoryResult, setMemoryResult] = useState<string | null>(null);
  const sendMemoryEdit = async () => {
    const message = memoryMsg.trim();
    if (!message || memoryEditing) return;
    setMemoryEditing(true);
    setMemoryResult(null);
    try {
      const res = await fetch('/api/profile/memory-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) {
        setMemoryResult('Something went wrong — try again.');
      } else {
        setMemoryResult(data.summary || 'Updated.');
        if (data.changed) { setMemoryMsg(''); onSaved(); }
      }
    } catch {
      setMemoryResult('Connection error — try again.');
    } finally {
      setMemoryEditing(false);
    }
  };

  // Document upload flow — same L1-profile pipeline as the chat composer's
  // attach button (POST /api/documents/upload), just triggered from Settings.
  const docFlowRef = useRef<UseDocumentUploadFlowReturn | null>(null);
  const attachment = useAttachedFiles();

  // One Send action for both the text edit and attachments — if valid files
  // are staged, send submits the document-upload job (with the typed note as
  // optional context); otherwise it sends the typed text as a memory edit.
  const hasDocsToSend = attachment.hasValidFiles;
  const canSubmitComposer = !memoryEditing && (!!memoryMsg.trim() || hasDocsToSend);

  const sendComposer = () => {
    if (!canSubmitComposer) return;
    if (hasDocsToSend) {
      const validFiles = attachment.fileResults.filter(r => r.error === null).map(r => r.file);
      docFlowRef.current?.submitUpload({
        files: validFiles,
        skipReview: attachment.skipReview,
        message: memoryMsg.trim() || undefined,
      });
      attachment.clearAll();
      setMemoryMsg('');
    } else {
      sendMemoryEdit();
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

  const memoryBadgeCount = profile?.pending_changes?.length ?? 0;

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">Settings</div>
        </div>
        {onClose && (
          <div className="ph-right">
            <button className="settings-modal-close" title="Close" onClick={onClose}>
              <Icon name="x" size={16} />
            </button>
          </div>
        )}
      </div>
      <div className="settings-shell">
        <div className="settings-nav">
          <div className={`settings-nav-item ${tab === 'profile' ? 'active' : ''}`} onClick={() => setTab('profile')}>
            <Icon name="user" size={15} /> Profile
          </div>
          <div className={`settings-nav-item ${tab === 'memory' ? 'active' : ''}`} onClick={() => setTab('memory')}>
            <Icon name="brain" size={15} /> Memory
            {memoryBadgeCount > 0 && <span className="nav-badge" />}
          </div>
        </div>

        <div className="settings-content">
          {saveError && (
            <div style={{ fontSize: 12, color: '#f87171', padding: '8px 12px', background: 'rgba(248,113,113,0.08)', borderRadius: 6, marginBottom: 16 }}>
              {saveError}
            </div>
          )}

          {tab === 'profile' && (
            <div className="settings-group">
              <div className="settings-group-title">Profile</div>

              <div className="settings-row">
                <div className="k">Avatar</div>
                <div className="v-wrap">
                  {avatarError && <span style={{ fontSize: 11, color: 'var(--danger)' }}>{avatarError}</span>}
                  {avatarUrl && (
                    <button className="btn btn-sm btn-ghost" disabled={saving} onClick={removeAvatar}>Remove</button>
                  )}
                  <button className="btn btn-sm btn-ghost" disabled={saving} onClick={() => avatarInputRef.current?.click()}>
                    {avatarUrl ? 'Change' : 'Upload'}
                  </button>
                  <input ref={avatarInputRef} type="file" accept="image/*" onChange={onAvatarPick} style={{ display: 'none' }} />
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="Profile" style={{ width: 32, height: 32, borderRadius: '50%', objectFit: 'cover' }} />
                  ) : (
                    <div className="avatar" style={{ width: 32, height: 32, fontSize: 14 }}>
                      {(profile?.name || 'Y')[0]?.toUpperCase()}
                    </div>
                  )}
                </div>
              </div>

              <div className="settings-row">
                <div className="k">Full name</div>
                <div className="v-wrap">
                  {editName ? (
                    <>
                      <input
                        className="num-input" style={{ minWidth: 200 }}
                        value={nameVal}
                        onChange={e => setNameVal(e.target.value)}
                      />
                      <button className="btn btn-sm btn-ghost" onClick={() => { setEditName(false); setNameVal(profile?.name ?? ''); }}>Cancel</button>
                      <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { if (await save({ name: nameVal })) setEditName(false); }}>Save</button>
                    </>
                  ) : (
                    <>
                      <span className="v">{profile?.name || '—'}</span>
                      <button className="btn btn-sm btn-ghost" onClick={() => setEditName(true)}>Edit</button>
                    </>
                  )}
                </div>
              </div>

            </div>
          )}

          {tab === 'memory' && (<>
            <div className="settings-memory-tabs">
              <button
                type="button"
                className={`settings-memory-tab ${memorySubTab === 'knows' ? 'active' : ''}`}
                onClick={() => setMemorySubTab('knows')}
              >
                About You<span className="settings-memory-tab-count">{situations.length + (profile?.style_notes?.length ?? 0)}</span>
              </button>
              <button
                type="button"
                className={`settings-memory-tab ${memorySubTab === 'data' ? 'active' : ''}`}
                onClick={() => setMemorySubTab('data')}
              >
                Import Memory
              </button>
            </div>

            {memorySubTab === 'knows' && (<>
              {memoryBadgeCount > 0 && (
                <div className="settings-group settings-suggested">
                  <button
                    type="button"
                    className="settings-suggested-header"
                    onClick={() => setSuggestedOpen(o => !o)}
                    aria-expanded={suggestedOpen}
                  >
                    <span className="settings-group-title">Suggested updates</span>
                    <span className="settings-suggested-count">{memoryBadgeCount}</span>
                    <span style={{ flex: 1 }} />
                    <Icon name={suggestedOpen ? 'x' : 'chevronDown'} size={13} />
                  </button>
                  {suggestedOpen && (<>
                    <div className="settings-group-sub">Noticed from recent sessions — nothing changes until you accept.</div>
                    {profile!.pending_changes.map(change => (
                      <div key={change.field} className="settings-row">
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="v" style={{ textAlign: 'left', whiteSpace: 'normal' }}>{describePendingChange(change.field, change.proposed_value)}</div>
                          <div style={{ fontSize: 11, color: 'var(--muted)' }}>{change.reason}</div>
                        </div>
                        <div className="v-wrap">
                          <button
                            className="btn btn-sm btn-ghost"
                            disabled={resolvingField === change.field}
                            onClick={() => resolvePendingChange(change.field, 'dismiss')}
                          >
                            Dismiss
                          </button>
                          <button
                            className="btn btn-sm btn-primary"
                            disabled={resolvingField === change.field}
                            onClick={() => resolvePendingChange(change.field, 'accept')}
                          >
                            Accept
                          </button>
                        </div>
                      </div>
                    ))}
                  </>)}
                </div>
              )}

              <div className="settings-group">
                <div className="set-header">
                  <div className="set-label">Facts About You</div>
                  <div className="set-header-line" />
                  <div className="set-header-count">
                    {situations.length > 0 ? `${situations.length} ${situations.length === 1 ? 'entry' : 'entries'}` : 'Not set'}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
                  {situations.map((text, i) => (
                    editingSituation?.index === i ? (
                      <div key={i} className="memory-fact-edit">
                        <textarea
                          autoFocus
                          rows={2}
                          value={editingSituation.draft}
                          onChange={e => setEditingSituation({ index: i, draft: e.target.value })}
                        />
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <button className="btn btn-accent btn-sm" onClick={commitSituation}>Done</button>
                          <button className="btn btn-ghost btn-sm" onClick={() => setEditingSituation(null)}>Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <div key={i} className="memory-fact-row" onClick={() => startEditSituation(i)}>
                        <div className="memory-fact-text">
                          {text}
                          {factWarning(text, factQuality[text]?.reason) && (
                            <div className="memory-fact-vague">
                              <span className="memory-fact-vague-badge">!</span>
                              {factWarning(text, factQuality[text]?.reason)}
                              {factQuality[text]?.rewrite && (
                                <button
                                  type="button"
                                  className="memory-fact-rewrite-btn"
                                  onClick={e => { e.stopPropagation(); applyFactRewrite(i, factQuality[text]!.rewrite!); }}
                                >
                                  Rewrite as a fact
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                        <button
                          className="memory-fact-remove" title="Forget this"
                          onClick={e => { e.stopPropagation(); removeSituation(i); }}
                        >
                          <Icon name="x" size={13} />
                        </button>
                      </div>
                    )
                  ))}
                  {editingSituation?.index === situations.length && (
                    <div className="memory-fact-edit">
                      <textarea
                        autoFocus
                        rows={2}
                        placeholder="describe a situation…"
                        value={editingSituation.draft}
                        onChange={e => setEditingSituation({ index: situations.length, draft: e.target.value })}
                      />
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <button className="btn btn-accent btn-sm" onClick={commitSituation}>Done</button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setEditingSituation(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                  <button type="button" className="memory-add-btn" onClick={addSituation}>+ Add a fact</button>
                </div>
              </div>

              {/* ponytail: no session event log yet — needs a backend feed of
                  per-session moments before this can show real entries. */}
              <div className="settings-group">
                <div className="set-header">
                  <div className="set-label">Session Moments</div>
                  <div className="set-header-line" />
                  <div className="set-header-count">Not tracked</div>
                </div>
                <div className="memory-stub" style={{ marginTop: 12 }}>
                  Session-by-session moments (stuck points, breakthroughs) aren&apos;t tracked yet.
                </div>
              </div>

              <div className="settings-group">
                <div className="set-header">
                  <div className="set-label">Insights</div>
                  <div className="set-header-line" />
                  <div className="set-header-count">
                    {(profile?.style_notes ?? []).length} inferred
                  </div>
                </div>
                <div style={{ marginTop: 6, fontSize: '12.5px', color: 'var(--muted)' }}>Inferred, not stated. Disagree and it&apos;s dropped for good.</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
                  {(profile?.style_notes ?? []).length === 0 && <div className="memory-stub">Nothing noticed yet.</div>}
                  {(profile?.style_notes ?? []).map((note, i) => (
                    <div key={i} className="memory-fact-row" style={{ cursor: 'default' }}>
                      <div className="memory-fact-text">
                        {note.note}
                        <div style={{ marginTop: 5, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)' }}>
                          {note.category}{note.added_at ? ` · ${note.added_at}` : ''}
                        </div>
                      </div>
                      <button className="btn btn-ghost btn-sm btn-disagree" onClick={() => removeStyleNote(i)}>Disagree</button>
                    </div>
                  ))}
                </div>
              </div>

            </>)}

            {memorySubTab === 'data' && (<>
              <div className="settings-group">
                <div className="set-header">
                  <div className="set-label">Pause &amp; export</div>
                  <div className="set-header-line" />
                </div>
                <div className="settings-row" style={{ marginTop: 12, border: '1px solid var(--border)', borderRadius: 'var(--r)', padding: '15px 17px', background: 'var(--card)' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '13.5px', color: 'var(--fg)' }}>Pause memory</div>
                    <div style={{ marginTop: 5, fontSize: '12.5px', color: 'var(--muted)' }}>Keeps everything, but the mentor answers as if it knew none of it.</div>
                  </div>
                  {/* ponytail: no pause flag on the profile yet — wire this up when the prompt assembler can skip L1 context on demand. */}
                  <button className="btn btn-ghost btn-sm" disabled title="Not available yet">Coming soon</button>
                </div>
                <div className="settings-row" style={{ marginTop: 10, border: '1px solid var(--border)', borderRadius: 'var(--r)', padding: '15px 17px', background: 'var(--card)' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '13.5px', color: 'var(--fg)' }}>Export memory</div>
                    <div style={{ marginTop: 5, fontSize: '12.5px', color: 'var(--muted)' }}>Download everything on this page as JSON.</div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={exportMemory}>Export</button>
                </div>
              </div>

              <div className="settings-group">
                <div className="set-header">
                  <div className="set-label danger">Start over</div>
                  <div className="set-header-line" />
                </div>
                <div className="danger-card" style={{ marginTop: 12 }}>
                  <div style={{ fontSize: '13.5px', color: 'var(--fg-dim)' }}>
                    Deletes every item, focus area, and teaching preference. Your chat history stays. This cannot be undone.
                  </div>
                  {confirmReset ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--danger)' }}>TYPE &quot;WIPE&quot; TO CONFIRM</span>
                      <input
                        className="num-input"
                        style={{ width: 110, fontFamily: 'var(--mono)', fontSize: 12, borderColor: 'var(--danger-line)' }}
                        value={wipeText}
                        placeholder="WIPE"
                        onChange={e => setWipeText(e.target.value)}
                      />
                      <button className="danger-btn" disabled={saving || wipeText.trim().toUpperCase() !== 'WIPE'} onClick={handleReset}>
                        Delete everything
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => { setConfirmReset(false); setWipeText(''); }}>Cancel</button>
                    </div>
                  ) : (
                    <button className="danger-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setConfirmReset(true)}>Wipe all memory</button>
                  )}
                </div>
              </div>
            </>)}
          </>)}
        </div>
      </div>

      {tab === 'memory' && memorySubTab === 'data' && (
        <div className="settings-memory-composer">
          {memoryResult && <div className="settings-memory-result">{memoryResult}</div>}
          <div className="settings-memory-status">
            <DocumentUploadFlow
              sessionId="memory-settings"
              existingStyleNotes={profile?.style_notes}
              flowRef={docFlowRef}
            />
          </div>
          <div className="settings-memory-composer-box">
            <AttachmentPreview
              fileResults={attachment.fileResults}
              warning={attachment.warning}
              skipReview={attachment.skipReview}
              disabled={memoryEditing}
              onRemove={attachment.removeFile}
              onClearAll={attachment.clearAll}
              onToggleSkipReview={attachment.toggleSkipReview}
            />
            <div className="settings-memory-composer-row">
              <input
                value={memoryMsg}
                placeholder="Tell it what to change or remove…"
                disabled={memoryEditing}
                onChange={e => setMemoryMsg(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') sendComposer(); }}
              />
              <AttachButton disabled={memoryEditing} onSelect={attachment.selectFiles} />
              <button
                className="icon-btn" title="Send" aria-label="Send"
                disabled={!canSubmitComposer}
                onClick={sendComposer}
              >
                <Icon name="arrowUp" />
              </button>
            </div>
          </div>
        </div>
      )}
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

