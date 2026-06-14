'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing } from './ui';
import { MODES, type MessageItem, type ModeId, type ToneId, type Topic } from './data';
import { ChatUploadButton } from './chat/ChatUploadButton';
import { UploadMessage } from './chat/UploadMessage';
import { useFileUpload, type UploadStatus } from '@/lib/chat-upload/useFileUpload';
import { useSessionPersistence, type Message as PersistenceMessage, type SessionEndResult } from '@/lib/session-persistence/useSessionPersistence';
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

function Composer({ mode, tone, onSend, busy, disabled, uploadElement, suggestions, onSuggestionClick }: {
  mode: ModeId;
  tone: ToneId;
  onSend: (text: string) => void;
  busy: boolean;
  disabled?: boolean;
  uploadElement?: React.ReactNode;
  suggestions?: string[];
  onSuggestionClick?: (text: string) => void;
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
    if (!t || busy || disabled) return;
    setVal('');
    if (ref.current) ref.current.style.height = 'auto';
    onSend(t);
  };

  const isEval = mode === 'evaluation';
  const showChips = !busy && !isEval && suggestions && suggestions.length > 0 && !val;
  return (
    <div className="composer">
      {isEval && (
        <div className="eval-flag"><span className="dot" /> Evaluation mode — your answer is graded</div>
      )}
      {showChips && (
        <div className="suggestions">
          {suggestions.map(s => (
            <button key={s} className="suggestion-chip" onClick={() => onSuggestionClick?.(s)}>{s}</button>
          ))}
        </div>
      )}
      <div className="composer-inner">
        <div className={`composer-box ${focus ? 'focus' : ''}`}>
          <textarea
            ref={ref} value={val} rows={1}
            disabled={disabled}
            placeholder={isEval ? 'Type your answer…' : 'Reply to your mentor…'}
            onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
            onChange={e => { setVal(e.target.value); grow(); }}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          />
          <div className="composer-tools">
            {uploadElement}
            <button className="tool-btn" title="Code block">{'</>'}</button>
            <div className="spacer" />
            <span className="tag" style={{ marginRight: 2 }}>mode: {mode}</span>
            <button className="send-btn" onClick={submit} disabled={busy || disabled || !val.trim()} title="Send">
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

export function ChatPanel({ sessionId, sessionTitle, mode, setMode, tone, onNav, onSessionSaved, onSessionEnd, topics = [] }: {
  sessionId: string;
  sessionTitle?: string;
  mode: ModeId;
  setMode: (m: ModeId) => void;
  tone: ToneId;
  onNav: (v: string) => void;
  onSessionSaved?: () => void;
  onSessionEnd?: (result: SessionEndResult) => void;
  topics?: Topic[];
}) {
  const fallback = { id: sessionId, title: 'New session', cat: 'Topic', date: 'now' };
  const session = sessionTitle ? { ...fallback, title: sessionTitle } : fallback;
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Upload state: track whether an upload is in progress for non-blocking verification
  const [uploadActive, setUploadActive] = useState(false);

  // Session persistence hook — manages session lifecycle, message persistence, recovery
  const {
    sessionId: persistenceSessionId,
    isEnding,
    error: persistenceError,
    createSession: persistenceCreateSession,
    persistMessages,
    endSession: persistenceEndSession,
    recoverOrphanedMessages,
    retryCreateSession,
  } = useSessionPersistence();

  // File upload hook — manages submission, polling, retries independently of chat
  const {
    state: uploadState,
    submit: submitUpload,
    retry: retryUpload,
    refreshStatus: refreshUploadStatus,
    reset: resetUpload,
  } = useFileUpload({
    sessionId: backendSessionId ?? '',
    onReady: (info) => {
      // Insert system message when extraction is ready (Req 6.9)
      const systemMsg: MessageItem = {
        who: 'system',
        text: `📎 ${info.filename} is now available to your mentor. ${info.summary}`,
        _id: 'sys-upload-' + info.jobId,
      };
      setMsgs(prev => [...prev, systemMsg]);
    },
    onStatusChange: (status) => {
      const activeStatuses = new Set<UploadStatus>(['uploading', 'pending', 'processing', 'ready']);
      setUploadActive(activeStatuses.has(status));
    },
  });

  // Track the selected file for submission
  const pendingFileRef = useRef<File | null>(null);

  const greetedRef = useRef(false);

  // Recover orphaned messages from localStorage on mount (Req 3.5, 3.6, 3.7)
  useEffect(() => {
    recoverOrphanedMessages();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync persistence hook's sessionId into local backendSessionId state
  useEffect(() => {
    if (persistenceSessionId && !backendSessionId) {
      setBackendSessionId(persistenceSessionId);
    }
  }, [persistenceSessionId, backendSessionId]);

  useEffect(() => {
    greetedRef.current = false;

    // Fresh session: resume an unsaved draft if present, else let the auto-greet run.
    if (sessionId === 'new') {
      try {
        const raw = localStorage.getItem(DRAFT_KEY);
        if (raw) {
          const draft = JSON.parse(raw) as { msgs: MessageItem[]; backendSessionId?: string };
          if (draft.msgs?.length > 0) {
            setMsgs(draft.msgs);
            if (draft.backendSessionId) setBackendSessionId(draft.backendSessionId);
            greetedRef.current = true; // skip greeting — conversation already started
            return;
          }
        }
      } catch {}
      setMsgs([]);
      return;
    }

    // Existing backend session — fetch stored messages
    let cancelled = false;
    setMsgs([]);
    setBusy(true);
    fetch(`/api/sessions/${sessionId}`)
      .then(r => {
        if (!r.ok) throw new Error('Failed to load session');
        return r.json();
      })
      .then(data => {
        if (cancelled) return;
        if (data.messages && data.messages.length > 0) {
          const loaded: MessageItem[] = data.messages.map((m: { id?: string; role: string; content: string }, i: number) => ({
            who: (m.role === 'assistant' || m.role === 'mentor') ? 'mentor' as const : 'user' as const,
            text: m.content,
            _id: m.id || `loaded${i}`,
          }));
          setMsgs(loaded);
          setBackendSessionId(sessionId);
          greetedRef.current = true; // skip auto-greet — history loaded
        } else if (data.status === 'ended') {
          // Ended session with no saved messages — show placeholder, suppress auto-greet
          setMsgs([{ who: 'system' as const, text: 'This session ended with no saved messages.', _id: 'empty-ended' }]);
          setBackendSessionId(sessionId);
          greetedRef.current = true;
        }
      })
      .catch(() => {
        // If fetch fails (session not saved yet), let auto-greet handle it
        if (!cancelled) setMsgs([]);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });

    return () => { cancelled = true; };
  }, [sessionId]);

  // Auto-greet: only runs for fresh sessions (sessionId === 'new'), never for sidebar-loaded sessions
  useEffect(() => {
    if (greetedRef.current) return;
    if (sessionId !== 'new') return; // existing sessions show their stored history, not a new greeting
    greetedRef.current = true;
    let cancelled = false;
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
      .then(({ text: reply, suggestions: chips }) => {
        if (cancelled) return;
        setMsgs([{ who: 'mentor', text: (reply || '').trim() || "Let's get started — what do you want to tackle first?", _id: 'greet0' }]);
        setSuggestions(Array.isArray(chips) ? chips : []);
        // NOTE: no session is created here. The greeting alone must not create a
        // backend session — that produced phantom empty sessions on every open.
        // The session is created lazily on the user's first action (send/upload).
      })
      .catch(() => {
        if (cancelled) return;
        setMsgs([{ who: 'mentor', text: "Let's get started — what do you want to tackle first?", _id: 'greet0' }]);
      })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
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
        backendSessionId, // resume the same backend session after a reload
        savedAt: new Date().toISOString(),
      }));
    } catch {}
  }, [msgs, sessionId, session.title, session.cat, backendSessionId]);

  // Auto-save the conversation to the backend after every exchange (debounced),
  // so history persists even if the user never clicks "End session".
  useEffect(() => {
    if (!backendSessionId || msgs.length === 0) return;
    const apiMessages = msgs
      .filter(m => m.who === 'mentor' || m.who === 'user')
      .map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
    // Derive a readable chat name from the first user message (fallback to topic).
    const firstUser = msgs.find(m => m.who === 'user')?.text?.trim();
    const derivedTitle = firstUser
      ? (firstUser.length > 48 ? firstUser.slice(0, 48) + '…' : firstUser)
      : session.title;
    const t = setTimeout(() => {
      fetch(`/api/sessions/${backendSessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: apiMessages, topic: session.title, title: derivedTitle }),
      }).catch(() => {});
    }, 800);
    return () => clearTimeout(t);
  }, [msgs, backendSessionId, session.title]);

  // Create the backend session exactly once, lazily, on the user's first action.
  const creatingRef = useRef(false);
  const ensureSession = useCallback(async (firstUserText?: string): Promise<string | null> => {
    if (backendSessionId) return backendSessionId;
    if (creatingRef.current) return null; // a creation is already in flight
    creatingRef.current = true;
    try {
      // Use the persistence hook's createSession which handles retry + localStorage + error state
      const id = await persistenceCreateSession(mode, session.title);
      if (id) {
        setBackendSessionId(id);
        onSessionSaved?.(); // refresh the sidebar so the new chat appears
      }
      return id;
    } catch {
      return null;
    } finally {
      creatingRef.current = false;
    }
  }, [backendSessionId, mode, session.title, onSessionSaved, persistenceCreateSession]);

  const send = useCallback(async (text: string) => {
    const userMsg: MessageItem = { who: 'user', text, _id: 'u' + Date.now() };
    setMsgs(prev => [...prev, userMsg]);
    setSuggestions([]);
    setBusy(true);
    try {
      const sid = backendSessionId || await ensureSession(text);
      const allHistory = [...msgs, userMsg]
        .filter(m => m.who === 'mentor' || m.who === 'user')
        .map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
      // Anthropic requires the first message to be from 'user' — drop any leading assistant turns
      const firstUser = allHistory.findIndex(m => m.role === 'user');
      const history = firstUser > 0 ? allHistory.slice(firstUser) : allHistory;
      const res = await fetch('/api/mentor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: session.title, mode, tone, messages: history, sessionId: sid }),
      });
      const { text: reply, suggestions: chips } = await res.json();
      setSuggestions(Array.isArray(chips) ? chips : []);
      const mentorText = (reply || '').trim() || "Let me think about that differently — can you say more about where you're stuck?";
      setMsgs(prev => [...prev, { who: 'mentor', text: mentorText, _id: 'm' + Date.now() }]);

      // Persist messages via the session persistence hook (Req 8.2)
      const now = new Date().toISOString();
      const userPersistMsg: PersistenceMessage = { role: 'user', content: text, timestamp: now };
      const mentorPersistMsg: PersistenceMessage = { role: 'mentor', content: mentorText, timestamp: now };
      persistMessages(userPersistMsg, mentorPersistMsg);
    } catch {
      setMsgs(prev => [...prev, { who: 'mentor', text: "I'm having trouble reaching my notes right now — try that again in a moment.", _id: 'm' + Date.now() }]);
    } finally {
      setBusy(false);
    }
  }, [msgs, mode, tone, session.title, backendSessionId, ensureSession, persistMessages]);

  const endSession = useCallback(async () => {
    localStorage.removeItem(DRAFT_KEY);
    if (msgs.length < 2) { onNav('summary'); return; }

    // Use the persistence hook's endSession which handles loading state, timeout, and cleanup (Req 8.4, 8.5, 8.9)
    // Pass backendSessionId as fallback for restored sessions where sessionIdRef.current is null
    const result = await persistenceEndSession(backendSessionId ?? undefined);

    if (result) {
      // Update sidebar with the completed session title from SessionEndResult (Req 8.5)
      onSessionSaved?.();
      onSessionEnd?.(result);
      // Clear session_id from state and localStorage on successful end
      setBackendSessionId(null);
    } else {
      // If endSession returned null, the hook sets its own error state.
      // We still do a fallback save for the messages if we have a backendSessionId.
      if (backendSessionId) {
        const apiMessages = msgs
          .filter(m => m.who === 'mentor' || m.who === 'user')
          .map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
        await fetch(`/api/sessions/${backendSessionId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: apiMessages, mode, topic: session.title }),
        }).catch(() => {});
      }
      // Don't navigate on failure — let user retry via error state
      return;
    }

    // Note: Ending the session does NOT cancel the ingestion pipeline.
    // If an upload is still being processed, the pipeline continues to completion
    // in the background (Requirement 7.7). The JobRecord and ImmediateContext
    // operations are independent of session state.
    onNav('summary');
  }, [msgs, session, mode, onNav, onSessionSaved, onSessionEnd, backendSessionId, persistenceEndSession]);

  /**
   * Handle file selection from the ChatUploadButton.
   * Stores the file reference for submission with the next message or immediately.
   */
  const handleFileSelected = useCallback((file: File) => {
    pendingFileRef.current = file;
    if (backendSessionId) {
      submitUpload(file);
      pendingFileRef.current = null;
    } else {
      // No session yet — create one; the effect below submits the pending file
      // once the upload hook re-renders with the new session id.
      ensureSession();
    }
  }, [backendSessionId, submitUpload, ensureSession]);

  // Submit a file that was selected before the session existed, once it does.
  useEffect(() => {
    if (backendSessionId && pendingFileRef.current) {
      const f = pendingFileRef.current;
      pendingFileRef.current = null;
      submitUpload(f);
    }
  }, [backendSessionId, submitUpload]);

  /**
   * Handle file removal from the ChatUploadButton preview chip.
   */
  const handleFileRemoved = useCallback(() => {
    pendingFileRef.current = null;
    if (uploadState.status === 'idle') {
      resetUpload();
    }
  }, [uploadState.status, resetUpload]);

  /**
   * Determine if the attachment button should be disabled.
   * Disabled while an upload is in progress (uploading or polling).
   * Re-enabled on terminal states, retries exhausted, or idle.
   */
  const isAttachmentDisabled = (() => {
    if (!backendSessionId) return true; // No session yet
    if (uploadState.status === 'idle') return false;
    if (uploadState.retriesExhausted) return false;
    if (uploadState.status === 'failed' && !uploadState.isActive) return false;
    if (uploadState.status === 'done' || uploadState.status === 'timeout' || uploadState.status === 'connection_lost') return false;
    return uploadState.isActive;
  })();

  /**
   * Whether to show the retry button on the UploadMessage.
   */
  const showRetryButton = uploadState.status === 'failed' && !uploadState.retriesExhausted;

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">{session.title}</div>
          <div className="ph-sub">session · {session.cat.toLowerCase()} · {session.date}</div>
        </div>
        <div className="ph-right">
          <ModeBar mode={mode} onMode={setMode} />
          <button className="btn btn-sm btn-ghost" onClick={endSession} disabled={isEnding} title="End session">
            {isEnding ? 'Ending…' : 'End'}
          </button>
          <span className="pill ok"><span className="ind" /> active</span>
        </div>
      </div>

      <AlertStack topics={topics} onReview={() => onNav('dashboard')} />

      <div className="chat-body" ref={bodyRef}>
        <div className="chat-inner">
          {/* Session creation error state with retry button (Req 8.8) */}
          {persistenceError && (
            <div className="session-error">
              <div className="session-error-text">
                <Icon name="warn" size={16} />
                <span>{persistenceError}</span>
              </div>
              <button className="btn btn-sm btn-ghost" onClick={retryCreateSession}>
                Retry
              </button>
            </div>
          )}
          {msgs.map((m, i) =>
            m.who === 'verdict'
              ? <VerdictMsg key={m._id || i} item={m as any} />
              : m.who === 'system'
              ? <div key={m._id || i} className="system-msg">
                  <span className="system-msg-text">{m.text}</span>
                </div>
              : <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />
          )}
          {/* Upload message in the conversation timeline (Req 1.6) */}
          {uploadState.status !== 'idle' && uploadState.filename && uploadState.fileType && (
            <UploadMessage
              jobId={uploadState.jobId ?? ''}
              filename={uploadState.filename}
              fileType={uploadState.fileType}
              status={uploadState.status as Exclude<UploadStatus, 'idle'>}
              summary={uploadState.summary ?? undefined}
              error={uploadState.error ?? undefined}
              onRetry={showRetryButton ? retryUpload : undefined}
              onRefresh={uploadState.status === 'connection_lost' ? refreshUploadStatus : undefined}
            />
          )}
          {busy && <Typing />}
          {/* Loading indicator during session-end processing (Req 8.9) */}
          {isEnding && (
            <div className="session-ending-indicator">
              <Typing />
              <span className="session-ending-text">Ending session and generating summary…</span>
            </div>
          )}
        </div>
      </div>

      <Composer
        mode={mode}
        tone={tone}
        onSend={send}
        busy={busy}
        disabled={isEnding || !!persistenceError}
        suggestions={suggestions}
        onSuggestionClick={send}
        uploadElement={
          <ChatUploadButton
            sessionId={backendSessionId ?? ''}
            disabled={isAttachmentDisabled}
            onFileSelected={handleFileSelected}
            onFileRemoved={handleFileRemoved}
          />
        }
      />
    </div>
  );
}
