'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing } from './ui';
import { MODES, TONES, type MessageItem, type ModeId, type ToneId, type Topic } from './data';
import { TopicRenameInput } from './TopicCreation';
import { WelcomeScreen } from './WelcomeScreen';
import { SummaryBlockIndicator } from './SummaryBlockIndicator';
import { SubtopicWeightsModal, buildGoalCards } from './SubtopicWeightsModal';
import { UncertainRelevanceModal, type UncertainL1ScopeItem } from './UncertainRelevanceModal';
import { L1MemoryModal } from './L1MemoryModal';
import { MentorQuestionCard, QuickReplyOptions, looksLikeQuestion, type QuickReplyOption } from './QuestionCard';
import { TopicContextPanel } from './TopicContextPanel';
import type { CoreProfile } from '@/lib/mentorman-api';

// Must match _META_MARKER in unified-backend/app/services/topic_chat_service.py
const META_MARKER = '\x00META\x00';

// One entry from a topic's l1_scope (facts about you, judged against the
// topic — see .kiro/specs/topic-scoping).
export interface L1ScopeEntry {
  situation: string;
  verdict: 'relevant' | 'irrelevant' | 'uncertain';
  reason: string;
  userResolved?: boolean;
}

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

function Composer({ mode, tone, onSend, busy, disabled }: {
  mode: ModeId;
  tone: ToneId;
  onSend: (text: string) => void;
  busy: boolean;
  disabled?: boolean;
}) {
  const [val, setVal] = useState('');
  const [focus, setFocus] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  const grow = () => {
    const el = ref.current;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 180) + 'px'; }
  };

  const canSubmit = !!val.trim();

  const submit = () => {
    if (busy || disabled || !canSubmit) return;
    const text = val.trim();
    setVal('');
    if (ref.current) ref.current.style.height = 'auto';
    onSend(text);
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
            id="composer-textarea"
            disabled={disabled}
            placeholder={isEval ? 'Type your answer…' : 'Reply to your mentor…'}
            onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
            onChange={e => { setVal(e.target.value); grow(); }}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          />
          <div className="composer-tools">
            <button className="tool-btn" title="Code block">{'</>'}</button>
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

export function ChatPanel({ topicId, mode, setMode, tone, setTone, onNav, onTopicUpdated, onTopicCreated, topics = [], profile, userName }: {
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
  // Full l1_scope for the current topic (facts about you, see
  // .kiro/specs/topic-scoping) — source of truth for both the topic-open
  // uncertain-items modal and SubtopicWeightsModal's goal-card filtering.
  const [l1Scope, setL1Scope] = useState<L1ScopeEntry[]>([]);
  // l1_scope entries the classifier judged "uncertain" and the user hasn't
  // resolved yet — surfaced via UncertainRelevanceModal on topic open.
  const [uncertainItems, setUncertainItems] = useState<UncertainL1ScopeItem[]>([]);
  const [showUncertainModal, setShowUncertainModal] = useState(false);
  // Same modal, reused to gate opening the weights picker specifically on
  // uncertain situations/context that its goal cards would otherwise use.
  const [weightsGateItems, setWeightsGateItems] = useState<UncertainL1ScopeItem[]>([]);
  const [showWeightsGate, setShowWeightsGate] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const greetedRef = useRef(false);

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

    // Fetch topic metadata for title + surface any unresolved uncertain
    // l1_scope entries (see .kiro/specs/topic-scoping).
    fetch(`/api/topic/${topicId}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (cancelled) return;
        if (data?.title) setTopicTitle(data.title);
        const scope: L1ScopeEntry[] = data?.l1_scope || [];
        setL1Scope(scope);
        const uncertain = scope.filter(e => e.verdict === 'uncertain' && !e.userResolved);
        setUncertainItems(uncertain);
        setShowUncertainModal(uncertain.length > 0);
      })
      .catch(() => {});

    // Fetch messages
    fetch(`/api/topic/${topicId}/messages?limit=50`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        const messages = data.messages || [];
        const loaded: MessageItem[] = messages.map((m: { id?: string; type?: string; role?: string; content?: string; mode?: string; summary?: string; compactedRange?: { from: string; to: string }; messageCount?: number; tokenCount?: number }, i: number) => {
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
            label: m.mode ? m.mode.toUpperCase() : undefined,
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

  // Send a message to the topic. The backend streams the reply token-by-token
  // (a mentor turn can loop on a tool call before answering, so total time
  // can exceed what feels good for a single blocking wait — streaming is
  // what keeps it feeling responsive). A trailing "\x00META\x00{...}" marker
  // carries {mode, suggestions}, since those can't ride on headers once the
  // stream (and its 200) has already started.
  const send = useCallback(async (
    text: string,
    opts?: { attachments?: { name: string; size: number }[]; backendContent?: string },
  ) => {
    if (!topicId) return;
    const userMsg: MessageItem = { who: 'user', text, _id: 'u' + Date.now(), attachments: opts?.attachments };
    setMsgs(prev => [...prev, userMsg]);
    setSuggestions([]);
    setBusy(true);
    const mentorId = 'm' + Date.now();
    try {
      const res = await fetch(`/api/topic/${topicId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: opts?.backendContent ?? text, mode }),
      });

      // Pre-flight rejections (e.g. topic at capacity) come back as plain
      // JSON before any streaming starts — everything else is a stream.
      if (res.headers.get('content-type')?.includes('application/json')) {
        const data = await res.json();
        setMsgs(prev => [...prev, { who: 'mentor', text: data.error || "I'm having trouble — try again in a moment.", _id: 'err' + Date.now() }]);
        return;
      }
      if (!res.body) throw new Error('No response body');

      setMsgs(prev => [...prev, { who: 'mentor', text: '', _id: mentorId }]);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        const metaIdx = full.indexOf(META_MARKER);
        const visible = metaIdx === -1 ? full : full.slice(0, metaIdx);
        setMsgs(prev => prev.map(m => m._id === mentorId ? { ...m, text: visible } : m));
      }

      const metaIdx = full.indexOf(META_MARKER);
      const visibleFinal = metaIdx === -1 ? full : full.slice(0, metaIdx);
      let meta: { mode?: string; suggestions?: QuickReplyOption[] } | null = null;
      if (metaIdx !== -1) {
        try { meta = JSON.parse(full.slice(metaIdx + META_MARKER.length)); } catch { /* malformed trailer — show text as-is */ }
      }
      setMsgs(prev => prev.map(m => m._id === mentorId ? { ...m, text: visibleFinal, label: meta?.mode ? String(meta.mode).toUpperCase() : undefined } : m));
      setSuggestions(Array.isArray(meta?.suggestions) ? meta.suggestions : []);
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

  // Persist the user's answer for one uncertain l1_scope entry. Updates local
  // state optimistically so the weights-modal gate (below) and any later
  // reopen within this session see the resolved verdict immediately, without
  // waiting on the network round trip. The POST itself is fire-and-forget —
  // a failure just means it gets asked again next topic open, same as skipping.
  const resolveUncertain = useCallback((situation: string, relevant: boolean) => {
    if (!topicId) return;
    setL1Scope(prev => prev.map(e => e.situation === situation
      ? { ...e, verdict: relevant ? 'relevant' as const : 'irrelevant' as const, userResolved: true }
      : e
    ));
    fetch(`/api/topic/${topicId}/l1-scope/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ situation, relevant }),
    }).catch(() => {});
  }, [topicId]);

  // Export the full topic transcript (all messages, not just the loaded page)
  // as a local .md file for offline analysis.
  const [exporting, setExporting] = useState(false);
  const [showWeights, setShowWeights] = useState(false);
  const [showL1Memory, setShowL1Memory] = useState(false);

  // Opening the weights picker: if any situation/context text its goal
  // cards would use is still "uncertain" and unresolved, resolve those
  // right here first — same modal as topic-open, scoped to just this
  // subset — instead of silently proceeding with a stale/unfiltered card.
  // Whether opening the weights modal will auto-run from real scoped L1
  // memory (vs. falling back to the generic "Just revising" option) — drives
  // the small indicator dot on the chart icon below.
  const weightsUseL1Scope = useMemo(
    () => !!buildGoalCards(profile, topicTitle, l1Scope)[0]?.fromL1Scope,
    [profile, topicTitle, l1Scope]
  );

  const openWeights = useCallback(() => {
    const cardTexts = new Set(
      [...(profile?.learning_context_detail?.situations ?? []), profile?.learning_context_detail?.label].filter(Boolean) as string[]
    );
    const pending = l1Scope.filter(e => e.verdict === 'uncertain' && !e.userResolved && cardTexts.has(e.situation));
    if (pending.length > 0) {
      setWeightsGateItems(pending);
      setShowWeightsGate(true);
    } else {
      setShowWeights(true);
    }
  }, [profile, l1Scope]);
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
    <>
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
            title={weightsUseL1Scope ? 'Where should you focus? — uses your scoped L1 memory' : 'Where should you focus?'}
            aria-label="Where should you focus?"
            onClick={openWeights}
            style={{ position: 'relative' }}
          >
            <Icon name="chart" />
            {weightsUseL1Scope && (
              <span style={{
                position: 'absolute', top: 4, right: 4, width: 7, height: 7,
                borderRadius: '50%', background: 'var(--accent)',
              }} />
            )}
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
        l1Scope={l1Scope}
        onOpenL1Memory={() => setShowL1Memory(true)}
      />

      <L1MemoryModal
        open={showL1Memory}
        topicTitle={topicTitle}
        entries={l1Scope}
        profile={profile}
        onResolve={resolveUncertain}
        onClose={() => setShowL1Memory(false)}
      />

      <UncertainRelevanceModal
        open={showUncertainModal}
        topicTitle={topicTitle}
        items={uncertainItems}
        onAnswer={resolveUncertain}
        onClose={() => setShowUncertainModal(false)}
      />

      <UncertainRelevanceModal
        open={showWeightsGate}
        topicTitle={topicTitle}
        items={weightsGateItems}
        onAnswer={resolveUncertain}
        onClose={() => { setShowWeightsGate(false); setShowWeights(true); }}
      />

      <AlertStack topics={topics} onReview={() => onNav('dashboard')} />

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
              ? <MentorQuestionCard key={m._id || i} text={m.text} label={m.label} />
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
        </div>
      </div>

      <Composer
        mode={mode}
        tone={tone}
        onSend={send}
        busy={busy}
      />
    </div>
    <TopicContextPanel topicId={topicId} />
    </>
  );
}
