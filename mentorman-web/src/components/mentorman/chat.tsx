'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing } from './ui';
import { MODES, TONES, type MessageItem, type ModeId, type ToneId, type Topic } from './data';
import { OnboardingBanner } from './OnboardingBanner';
import { TopicRenameInput } from './TopicCreation';
import { WelcomeScreen } from './WelcomeScreen';
import { SummaryBlockIndicator } from './SummaryBlockIndicator';
import { SubtopicWeightsModal } from './SubtopicWeightsModal';
import { MentorQuestionCard, QuickReplyOptions, looksLikeQuestion, type QuickReplyOption } from './QuestionCard';
import { AttachButton } from './chat/AttachButton';
import { AttachmentPreview } from './chat/AttachmentPreview';
import { DocumentUploadFlow } from './chat/DocumentUploadFlow';
import { useAttachedFiles } from '@/lib/chat-upload/useAttachedFiles';
import type { UseDocumentUploadFlowReturn } from '@/lib/chat-upload/useDocumentUploadFlow';
import type { CoreProfile } from '@/lib/mentorman-api';

function ModeBar({ mode, onMode, locked }: { mode: ModeId; onMode: (m: ModeId) => void; locked?: boolean }) {
  return (
    <div className="modes" role="tablist" aria-label="Session mode">
      <span className="bar-label">mode</span>
      {MODES.map(m => (
        <div key={m.id}
             className={`mode-tab ${mode === m.id ? 'active' : ''} ${locked ? 'locked' : ''}`}
             onClick={() => { if (!locked) onMode(m.id); }}
             aria-disabled={locked || undefined}
             title={locked ? 'Mode is fixed for this chat — start a new topic to change it' : m.blurb}>
          {m.label}
        </div>
      ))}
    </div>
  );
}

// Collapsed by default — the mode bar already takes a lot of header space,
// and voice is changed far less often than mode. Click to reveal the options.
function ToneBar({ tone, onTone }: { tone: ToneId; onTone: (t: ToneId) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = TONES.find(t => t.id === tone) ?? TONES[0];

  useEffect(() => {
    if (!open) return;
    const onOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, [open]);

  return (
    <div className="tone-select" ref={ref}>
      <button
        className={`tone-select-trigger ${open ? 'open' : ''}`}
        onClick={() => setOpen(o => !o)}
        title={current.blurb}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="bar-label">voice</span>
        <span className="tone-select-current">{current.label}</span>
        <Icon name="chevronDown" size={11} />
      </button>
      {open && (
        <div className="tone-select-menu" role="listbox" aria-label="Mentor tone">
          {TONES.map(t => (
            <div
              key={t.id}
              role="option"
              aria-selected={tone === t.id}
              className={`tone-select-option ${tone === t.id ? 'active' : ''}`}
              onClick={() => { onTone(t.id); setOpen(false); }}
            >
              <span className="tone-select-option-label">{t.label}</span>
              <span className="tone-select-option-blurb">{t.blurb}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Composer({ mode, tone, onSend, busy, disabled, onUpload, sessionId, onDocumentSubmit }: {
  mode: ModeId;
  tone: ToneId;
  onSend: (text: string) => void;
  busy: boolean;
  disabled?: boolean;
  onUpload?: (file: File) => void;
  /** Session ID for the document uploader. */
  sessionId?: string;
  /** Called when Send submits staged document attachments. */
  onDocumentSubmit?: (payload: { files: File[]; skipReview: boolean; message?: string }) => void;
}) {
  const [val, setVal] = useState('');
  const [focus, setFocus] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachment = useAttachedFiles();
  const canAttach = !!(sessionId && onDocumentSubmit);

  const grow = () => {
    const el = ref.current;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 180) + 'px'; }
  };

  // One Send action for both text and attachments — if valid files are
  // staged, send submits the document-upload job (with the typed text as
  // optional context); otherwise it sends the typed text as a chat message.
  const hasDocsToSend = canAttach && attachment.hasValidFiles;
  const canSubmit = !!val.trim() || hasDocsToSend;

  const submit = () => {
    if (busy || disabled || !canSubmit) return;
    const text = val.trim();
    setVal('');
    if (ref.current) ref.current.style.height = 'auto';
    if (hasDocsToSend) {
      const validFiles = attachment.fileResults.filter(r => r.error === null).map(r => r.file);
      onDocumentSubmit!({ files: validFiles, skipReview: attachment.skipReview, message: text || undefined });
      attachment.clearAll();
    } else {
      onSend(text);
    }
  };

  const isEval = mode === 'evaluation';
  return (
    <div className="composer">
      {isEval && (
        <div className="eval-flag"><span className="dot" /> Evaluation mode — your answer is graded</div>
      )}
      <div className="composer-inner">
        <div className={`composer-box ${focus ? 'focus' : ''}`}>
          {canAttach && (
            <AttachmentPreview
              fileResults={attachment.fileResults}
              warning={attachment.warning}
              skipReview={attachment.skipReview}
              disabled={disabled}
              onRemove={attachment.removeFile}
              onClearAll={attachment.clearAll}
              onToggleSkipReview={attachment.toggleSkipReview}
            />
          )}
          <textarea
            ref={ref} value={val} rows={1}
            id="composer-textarea"
            disabled={disabled}
            placeholder={isEval ? 'Type your answer…' : 'Reply to your mentor…'}
            onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
            onChange={e => { setVal(e.target.value); grow(); }}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          />
          <div className="composer-tools">
            <button className="tool-btn" title="Code block">{'</>'}</button>
            {onUpload && (
              <>
                <button
                  className="tool-btn"
                  title="Upload résumé (PDF) or LeetCode (CSV)"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Icon name="upload" size={13} />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.csv"
                  style={{ display: 'none' }}
                  onChange={e => {
                    const file = e.target.files?.[0];
                    e.target.value = ''; // allow re-selecting the same file
                    if (file) onUpload(file);
                  }}
                />
              </>
            )}
            {canAttach && <AttachButton disabled={disabled} onSelect={attachment.selectFiles} />}
            <div className="spacer" />
            <button className="send-btn" onClick={submit} disabled={busy || disabled || !canSubmit} title="Send">
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

export function ChatPanel({ topicId, mode, setMode, tone, setTone, onNav, onTopicUpdated, onTopicCreated, topics = [], profile, userName, onStartDeferredOnboarding }: {
  topicId: string | null;
  mode: ModeId;
  setMode: (m: ModeId) => void;
  tone: ToneId;
  setTone: (t: ToneId) => void;
  onNav: (v: string) => void;
  onTopicUpdated?: () => void;
  onTopicCreated?: (topicId: string) => void;
  topics?: Topic[];
  profile?: CoreProfile | null;
  userName?: string;
  onStartDeferredOnboarding?: () => void;
}) {
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // Text typed on the welcome screen, held until the freshly-created topic's
  // history has finished loading (see the effect below).
  const [pendingFirst, setPendingFirst] = useState<string | null>(null);
  // Topic id whose history has finished loading — gates the pendingFirst send.
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<QuickReplyOption[]>([]);
  const [topicTitle, setTopicTitle] = useState<string>('New Topic');
  const bodyRef = useRef<HTMLDivElement>(null);
  const greetedRef = useRef(false);

  // Document upload flow controller ref — shared between DocumentUploadFlow and Composer
  const docFlowRef = useRef<UseDocumentUploadFlowReturn | null>(null);

  // Load messages when topicId changes
  useEffect(() => {
    if (!topicId) {
      setMsgs([]);
      setTopicTitle('New Topic');
      setLoadedFor(null);
      greetedRef.current = false;
      return;
    }
    setLoadedFor(null);
    let cancelled = false;
    setBusy(true);
    greetedRef.current = true;

    // Fetch topic metadata for title
    fetch(`/api/topic/${topicId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!cancelled && data?.title) setTopicTitle(data.title);
      })
      .catch(() => {});

    // Fetch messages
    fetch(`/api/topic/${topicId}/messages?limit=50`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        const messages = data.messages || [];
        const loaded: MessageItem[] = messages.map((m: { id?: string; type?: string; role?: string; content?: string; summary?: string; compactedRange?: { from: string; to: string }; messageCount?: number; tokenCount?: number }, i: number) => {
          if (m.type === 'summary') {
            return {
              who: 'summary' as const,
              text: m.summary || '',
              _id: m.id || `summary${i}`,
              summaryBlock: {
                type: 'summary' as const,
                id: m.id || `summary${i}`,
                summary: m.summary || '',
                compactedRange: m.compactedRange || { from: new Date().toISOString(), to: new Date().toISOString() },
                messageCount: m.messageCount || 0,
                tokenCount: m.tokenCount || 0,
              },
            };
          }
          return {
            who: (m.role === 'assistant' || m.role === 'mentor') ? 'mentor' as const : 'user' as const,
            text: m.content || '',
            _id: m.id || `loaded${i}`,
          };
        });
        setMsgs(loaded);
      })
      .catch(() => { if (!cancelled) setMsgs([]); })
      .finally(() => { if (!cancelled) { setBusy(false); setLoadedFor(topicId); } });

    return () => { cancelled = true; };
  }, [topicId]);

  // Auto-scroll on new messages. Includes `suggestions` — the options card
  // takes up its own space below chat-body (not an overlay), so chat-body
  // shrinks when it appears; without re-scrolling here, the tail of the last
  // message stays at the old scroll position and looks cut off behind it.
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy, suggestions]);

  // Send a message to the topic
  const send = useCallback(async (text: string) => {
    if (!topicId) return;
    const userMsg: MessageItem = { who: 'user', text, _id: 'u' + Date.now() };
    setMsgs(prev => [...prev, userMsg]);
    setSuggestions([]);
    setBusy(true);
    try {
      const res = await fetch(`/api/topic/${topicId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: text, mode }),
      });
      const data = await res.json();
      if (data.error) {
        setMsgs(prev => [...prev, { who: 'mentor', text: data.error, _id: 'err' + Date.now() }]);
      } else {
        setMsgs(prev => [...prev, { who: 'mentor', text: data.response, _id: 'm' + Date.now() }]);
        setSuggestions(Array.isArray(data.suggestions) ? data.suggestions : []);
      }
    } catch {
      setMsgs(prev => [...prev, { who: 'mentor', text: "I'm having trouble — try again in a moment.", _id: 'err' + Date.now() }]);
    } finally {
      setBusy(false);
    }
  }, [topicId, mode]);

  // Welcome screen: send the typed text into the topic the user picked, or —
  // when they picked "New topic" — create one first. A new topic's title is
  // derived from the message (first 100 chars), so there's no naming step.
  const startFromMessage = useCallback(async (text: string, existingTopicId: string | null) => {
    if (creating) return;
    if (existingTopicId) {
      // Same handoff as a fresh topic: hold the text until the thread loads.
      setPendingFirst(text);
      onTopicCreated?.(existingTopicId);
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const res = await fetch('/api/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: text.trim().slice(0, 100) }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setCreateError(data?.detail || 'Could not start that topic — please try again.');
        return;
      }
      const topic = await res.json();
      const newId = topic.topicId || topic.topic_id || topic.id;
      if (!newId) {
        setCreateError('Could not start that topic — please try again.');
        return;
      }
      setPendingFirst(text);
      onTopicCreated?.(newId);
    } catch {
      setCreateError('Connection error — please try again.');
    } finally {
      setCreating(false);
    }
  }, [creating, onTopicCreated]);

  // Send that first message only once this topic's history has loaded.
  // Sending during the load is silently discarded — the load ends with
  // setMsgs(loaded), which replaces the optimistic user message wholesale.
  // `busy` can't gate this: the load effect and this one run in the same
  // commit, where setBusy(true) hasn't applied yet — hence the explicit
  // "loaded this exact topic" marker.
  useEffect(() => {
    if (!topicId || pendingFirst === null || loadedFor !== topicId) return;
    const text = pendingFirst;
    setPendingFirst(null);
    send(text);
  }, [topicId, pendingFirst, loadedFor, send]);

  // Upload a résumé/LeetCode file mid-chat; status surfaces as a system
  // message in the thread (server accepts PDF/CSV, extracts in the
  // background, and context_assembler reads the chunks into every mentor
  // call afterward — see app/routers/ingest.py).
  const uploadFile = useCallback(async (file: File) => {
    const sysId = 'sys' + Date.now();
    setMsgs(prev => [...prev, { who: 'system', text: `Uploading ${file.name}…`, _id: sysId }]);
    try {
      const fd = new FormData();
      fd.append('files', file);
      const res = await fetch('/api/ingest', { method: 'POST', body: fd });
      const text = !res.ok
        ? (res.status === 400 ? 'Unsupported file — use a PDF or CSV.' : 'Upload failed — try again.')
        : `${file.name} uploaded — your mentor will use it shortly.`;
      setMsgs(prev => prev.map(m => (m._id === sysId ? { ...m, text } : m)));
    } catch {
      setMsgs(prev => prev.map(m => (m._id === sysId ? { ...m, text: 'Connection error — try again.' } : m)));
    }
  }, []);

  /**
   * Handle multi-format document upload submission from the composer's Send.
   * Delegates to the DocumentUploadFlow controller (non-blocking).
   * The chat session remains fully functional during upload processing.
   * Requirements: 5.3, 6.1, 9.3
   */
  const handleDocumentSubmit = useCallback((payload: { files: File[]; skipReview: boolean; message?: string }) => {
    if (!docFlowRef.current) return;
    // Add a system message to acknowledge the upload started
    const fileNames = payload.files.map(f => f.name).join(', ');
    setMsgs(prev => [...prev, {
      who: 'system',
      text: `Uploading ${payload.files.length} document${payload.files.length > 1 ? 's' : ''}: ${fileNames}`,
      _id: 'doc-upload-' + Date.now(),
    }]);
    // Trigger the upload flow — this is async but non-blocking for chat
    docFlowRef.current.submitUpload(payload);
  }, []);

  // Export the full topic transcript (all messages, not just the loaded page)
  // as a local .md file for offline analysis.
  const [exporting, setExporting] = useState(false);
  const [showWeights, setShowWeights] = useState(false);
  const exportTranscript = useCallback(async () => {
    if (!topicId || exporting) return;
    setExporting(true);
    try {
      const res = await fetch(`/api/topic/${topicId}`);
      if (!res.ok) throw new Error('failed to load topic');
      const topic = await res.json();
      const entries: Array<Record<string, any>> = topic.messages || [];

      const lines: string[] = [
        `# ${topic.title || 'Topic'}`,
        '',
        `- Mode: ${topic.mode || mode}`,
        `- Created: ${topic.createdAt || ''}`,
        `- Exported: ${new Date().toISOString()}`,
        '',
        '---',
        '',
      ];
      for (const e of entries) {
        if (e.type === 'summary') {
          const from = e.compactedRange?.from ?? '';
          const to = e.compactedRange?.to ?? '';
          lines.push(`> **[Compacted summary — ${e.messageCount ?? '?'} messages, ${from} to ${to}]**`, '');
          lines.push(e.summary || '', '');
        } else {
          const who = e.role === 'assistant' ? 'Mentor' : 'User';
          lines.push(`**${who}** _(${e.timestamp || ''})_`, '');
          lines.push(e.content || '', '');
          if (e.systemPrompt) {
            lines.push(
              '<details><summary>System prompt sent to the LLM (L1/L2/L3 context)</summary>',
              '',
              '```',
              e.systemPrompt,
              '```',
              '',
              '</details>',
              ''
            );
          }
        }
      }

      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const safeName = (topic.title || 'topic').replace(/[^a-z0-9-_ ]/gi, '').trim() || 'topic';
      a.href = url;
      a.download = `${safeName}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Best-effort feature — silently no-op on failure rather than
      // interrupting the chat with an error the user can't act on.
    } finally {
      setExporting(false);
    }
  }, [topicId, mode, exporting]);

  // No topic yet — the welcome screen doubles as topic creation: whatever the
  // user types opens a topic and becomes its first message.
  if (!topicId) {
    return (
      <WelcomeScreen
        userName={userName}
        busy={creating}
        error={createError}
        onStart={startFromMessage}
        onNav={onNav}
      />
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left">
          <TopicRenameInput
            topicId={topicId}
            currentTitle={topicTitle}
            onRenamed={(newTitle) => { setTopicTitle(newTitle); onTopicUpdated?.(); }}
          />
        </div>
        <div className="ph-right">
          {/* ponytail: mode + voice (tone) selectors hidden per request — remove `false &&` to re-enable; components/state kept intact. */}
          {false && <ModeBar mode={mode} onMode={setMode} locked={msgs.some(m => m.who === 'user')} />}
          {false && <ToneBar tone={tone} onTone={setTone} />}
          <button
            className="icon-btn"
            title="Where should you focus?"
            aria-label="Where should you focus?"
            onClick={() => setShowWeights(true)}
          >
            <Icon name="chart" />
          </button>
          <button
            className="icon-btn"
            title="Download full transcript (.md)"
            aria-label="Download full transcript"
            disabled={exporting || msgs.length === 0}
            onClick={exportTranscript}
          >
            <Icon name="download" />
          </button>
          <span className="pill ok"><span className="ind" /> active</span>
        </div>
      </div>

      <SubtopicWeightsModal
        open={showWeights}
        onClose={() => setShowWeights(false)}
        topicId={topicId}
        topicTitle={topicTitle}
        profile={profile}
      />

      <AlertStack topics={topics} onReview={() => onNav('dashboard')} />

      {profile?.profile_status === 'skipped' && onStartDeferredOnboarding && (
        <OnboardingBanner onComplete={onStartDeferredOnboarding} onDismiss={() => {}} />
      )}

      <div className="chat-body" ref={bodyRef}>
        <div className="chat-inner">
          {msgs.map((m, i) =>
            m.who === 'summary'
              ? <SummaryBlockIndicator key={m._id || i} summaryBlock={m.summaryBlock!} />
              : m.who === 'mentor' && !m.text
              ? null
              : m.who === 'verdict'
              ? <VerdictMsg key={m._id || i} item={m as any} />
              : m.who === 'system'
              ? <div key={m._id || i} className="system-msg">
                  <span className="system-msg-text">{m.text}</span>
                </div>
              : m.who === 'mentor' && looksLikeQuestion(m.text)
              ? <MentorQuestionCard key={m._id || i} text={m.text} />
              : <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />
          )}
          {busy && !(msgs[msgs.length - 1]?.who === 'mentor' && msgs[msgs.length - 1]?.text) && (
            <Typing label="Thinking, may check the web for current info…" />
          )}

          {!busy && suggestions.length > 0 && (
            <div className="chat-options">
              <QuickReplyOptions
                options={suggestions}
                onSelect={send}
                onTypeOwn={() => { setSuggestions([]); document.getElementById('composer-textarea')?.focus(); }}
                onClose={() => setSuggestions([])}
              />
            </div>
          )}

          {/* Document upload flow — renders inline, non-blocking (Req: 9.3) */}
          {topicId && (
            <DocumentUploadFlow
              sessionId={topicId}
              existingStyleNotes={profile?.style_notes}
              flowRef={docFlowRef}
            />
          )}
        </div>
      </div>

      <Composer
        mode={mode}
        tone={tone}
        onSend={send}
        busy={busy}
        onUpload={uploadFile}
        sessionId={topicId ?? undefined}
        onDocumentSubmit={topicId ? handleDocumentSubmit : undefined}
      />
    </div>
  );
}
