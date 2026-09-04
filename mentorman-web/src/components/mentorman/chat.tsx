'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing, ToolActivity } from './ui';
import { TONES, type MessageItem, type ToneId, type Topic } from './data';
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

// Must match _TOOL_MARKER in unified-backend/app/services/topic_chat_service.py.
// Zero or more of these can appear anywhere in the stream, interleaved with
// visible reply text, before the trailing META marker: each occurrence is
// `\x00TOOL\x00{"phase": "start"|"end", "name": "<tool>"}\n`.
const TOOL_MARKER = '\x00TOOL\x00';
const TOOL_MARKER_RE = /\x00TOOL\x00(\{.*?\})\n/g;

// This mentor's voice is direct/no-fluff — keep these short and in-character.
const TOOL_LABELS: Record<string, string> = {
  get_user_profile: 'Checking your profile',
  get_skill_state: 'Checking your progress',
  get_past_sessions: 'Recalling past sessions',
  search_documents: 'Searching your documents',
  search_other_topics: 'Searching other topics',
};

// Strips TOOL_MARKER occurrences out of the raw accumulated stream buffer and
// returns the cleaned text plus which tool(s) are currently mid-call (a
// "start" with no matching "end" yet) at this point in the buffer. Re-derived
// from the full buffer on every read, same as META_MARKER handling below —
// a marker split across two chunk boundaries just doesn't match yet and gets
// picked up once the rest has arrived. The model can call more than one tool
// per turn (sequentially) and can loop back for a second round, so this walks
// the ordered event list rather than tracking a single active/inactive flag.
function parseToolMarkers(full: string): { visible: string; activeTools: string[] } {
  const active: string[] = [];
  for (const m of full.matchAll(TOOL_MARKER_RE)) {
    try {
      const { phase, name } = JSON.parse(m[1]);
      if (phase === 'start') active.push(name);
      else if (phase === 'end') {
        const idx = active.indexOf(name);
        if (idx !== -1) active.splice(idx, 1);
      }
    } catch { /* malformed marker — ignore rather than leak it into the bubble */ }
  }
  return { visible: full.replace(TOOL_MARKER_RE, ''), activeTools: active };
}

// One entry from a topic's l1_scope (facts about you, judged against the
// topic — see .kiro/specs/topic-scoping).
export interface L1ScopeEntry {
  situation: string;
  verdict: 'relevant' | 'irrelevant' | 'uncertain';
  reason: string;
  userResolved?: boolean;
}

// Collapsed by default. Click to reveal the options.
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

function Composer({ tone, onSend, busy, disabled }: {
  tone: ToneId;
  // Resolves false when the message was rejected before it ever reached the
  // backend (e.g. topic at capacity) — the composer restores the text so
  // nothing typed is silently lost.
  onSend: (text: string) => Promise<boolean>;
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

  const submit = async () => {
    if (busy || disabled || !canSubmit) return;
    const text = val.trim();
    setVal('');
    if (ref.current) ref.current.style.height = 'auto';
    const ok = await onSend(text);
    if (!ok) setVal(text);
  };

  return (
    <div className="composer">
      <div className="composer-inner">
        <div className={`composer-box ${focus ? 'focus' : ''}`}>
          <textarea
            ref={ref} value={val} rows={1}
            id="composer-textarea"
            disabled={disabled}
            placeholder="Reply to your mentor…"
            onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
            onChange={e => { setVal(e.target.value); grow(); }}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          />
          <div className="composer-tools">
            <button className="tool-btn" title="Code block">{'</>'}</button>
            <div className="spacer" />
            <button className="send-btn" onClick={submit} disabled={busy || disabled || !canSubmit} title="Send">
              <Icon name="send" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Interleaves a "session ended" divider into the message list at each closed
// session's boundary. dividerTimes are ISO timestamps (topic.summaryBlocks[].
// lastMergedAt — when that sitting's messages were compacted on close); ISO
// strings sort lexically, so no Date parsing is needed to order them against
// message.timestamp. Messages without a timestamp (e.g. the in-flight
// streaming placeholder) just never trigger a divider — no crash.
//
// close-session only fires on a true end-of-sitting signal now (see
// closeTopicSession above), but pagehide+beforeunload can still both fire
// for the same tab close, and the backend force-closes on token-budget
// overflow independently — so back-to-back closes are still possible. Each
// of those is a genuine (if tiny) summaryBlock, but its messages get pruned
// from topic.messages once summarized, so nothing renders between the
// resulting dividers — back-to-back boundaries that read as duplicates
// (and, if compacted within the same minute, literally *look* identical
// once formatSessionEndLabel truncates to minute precision). Collapse any
// run of adjacent dividers into one (keeping the latest time) rather than
// stacking near-meaningless repeats.
function insertSessionDividers(msgs: MessageItem[], dividerTimes: string[]): MessageItem[] {
  if (!dividerTimes.length) return msgs;
  const sorted = [...dividerTimes].sort();
  const out: MessageItem[] = [];
  const pushDivider = (t: string) => {
    const last = out[out.length - 1];
    if (last?.who === 'session-end') {
      last.text = t;
      last._id = `sdiv-${t}`;
      return;
    }
    out.push({ who: 'session-end', text: t, _id: `sdiv-${t}` });
  };
  let di = 0;
  for (const m of msgs) {
    while (di < sorted.length && m.timestamp && sorted[di] <= m.timestamp) {
      pushDivider(sorted[di]);
      di++;
    }
    out.push(m);
  }
  while (di < sorted.length) {
    pushDivider(sorted[di]);
    di++;
  }
  return out;
}

function formatSessionEndLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Session ended';
  const date = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(d);
  const time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(d);
  return `Session ended · ${date}, ${time}`;
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

export function ChatPanel({ topicId, tone, setTone, onNav, onTopicUpdated, onTopicCreated, topics = [], profile, userName }: {
  topicId: string | null;
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
  // One entry per closed-and-compacted session (topic.summaryBlocks,
  // lastMergedAt — the moment that sitting's messages were summarized on
  // close). Used only to place a subtle "session ended" divider among the
  // loaded messages; see insertSessionDividers.
  const [sessionEndTimes, setSessionEndTimes] = useState<string[]>([]);
  // Same modal, reused to gate opening the weights picker specifically on
  // uncertain situations/context that its goal cards would otherwise use.
  const [weightsGateItems, setWeightsGateItems] = useState<UncertainL1ScopeItem[]>([]);
  const [showWeightsGate, setShowWeightsGate] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const greetedRef = useRef(false);

  // Sessions aren't idle-timed out, and switching topics in-app does NOT
  // close a session either — a topic window left open (including one you've
  // navigated away from to view another topic) stays open server-side. The
  // backend only closes a topic's session on a true end-of-sitting signal:
  // tab/browser close, here (`keepalive` lets the request outlive the
  // unload), or its own force-close on token-budget overflow.
  const closeTopicSession = useCallback((id: string | null) => {
    if (!id) return;
    fetch(`/api/topic/${id}/close-session`, { method: 'POST', keepalive: true }).catch(() => {});
  }, []);

  // Close the session for the currently open topic on tab/browser close.
  useEffect(() => {
    const onHide = () => closeTopicSession(topicId);
    window.addEventListener('pagehide', onHide);
    window.addEventListener('beforeunload', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      window.removeEventListener('beforeunload', onHide);
    };
  }, [topicId, closeTopicSession]);

  // Load messages when topicId changes
  useEffect(() => {
    if (!topicId) {
      setMsgs([]);
      setTopicTitle('New Topic');
      setSessionEndTimes([]);
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
        const blocks: { lastMergedAt?: string }[] = data?.summaryBlocks || [];
        setSessionEndTimes(blocks.map(b => b.lastMergedAt).filter((t): t is string => !!t));
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
        const loaded: MessageItem[] = messages.map((m: { id?: string; type?: string; role?: string; content?: string; mode?: string; summary?: string; compactedRange?: { from: string; to: string }; messageCount?: number; tokenCount?: number; timestamp?: string }, i: number) => {
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
            timestamp: m.timestamp,
          };
        });
        setMsgs(loaded);
      })
      .catch(() => { if (!cancelled) setMsgs([]); })
      .finally(() => { if (!cancelled) { setBusy(false); setLoadedFor(topicId); } });

    return () => {
      cancelled = true;
    };
  }, [topicId]);

  const displayMsgs = useMemo(
    () => insertSessionDividers(msgs, sessionEndTimes),
    [msgs, sessionEndTimes]
  );

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
  ): Promise<boolean> => {
    if (!topicId) return false;
    const userId = 'u' + Date.now();
    const userMsg: MessageItem = { who: 'user', text, _id: userId, attachments: opts?.attachments, timestamp: new Date().toISOString() };
    setMsgs(prev => [...prev, userMsg]);
    setSuggestions([]);
    setBusy(true);
    const mentorId = 'm' + Date.now();
    try {
      const res = await fetch(`/api/topic/${topicId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: opts?.backendContent ?? text, mode: 'topic' }),
      });

      // Pre-flight rejections (e.g. topic at capacity, chronological-order
      // conflict, context-assembly failure) come back as plain JSON before
      // any streaming starts — everything else is a stream. The message was
      // never persisted server-side, so drop the optimistic bubble rather
      // than leave it looking sent (the caller restores it into the input).
      if (res.headers.get('content-type')?.includes('application/json')) {
        const data = await res.json();
        setMsgs(prev => [
          ...prev.filter(m => m._id !== userId),
          { who: 'mentor', text: data.error ?? data.detail ?? "I'm having trouble — try again in a moment.", _id: 'err' + Date.now() },
        ]);
        return false;
      }
      if (!res.body) throw new Error('No response body');

      setMsgs(prev => [...prev, { who: 'mentor', text: '', _id: mentorId, timestamp: new Date().toISOString() }]);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        const { visible: deToolMarked, activeTools } = parseToolMarkers(full);
        const metaIdx = deToolMarked.indexOf(META_MARKER);
        const visible = metaIdx === -1 ? deToolMarked : deToolMarked.slice(0, metaIdx);
        setMsgs(prev => prev.map(m => m._id === mentorId ? { ...m, text: visible, activeTools } : m));
      }

      const { visible: deToolMarkedFinal } = parseToolMarkers(full);
      const metaIdx = deToolMarkedFinal.indexOf(META_MARKER);
      const visibleFinal = metaIdx === -1 ? deToolMarkedFinal : deToolMarkedFinal.slice(0, metaIdx);
      let meta: { mode?: string; suggestions?: QuickReplyOption[] } | null = null;
      if (metaIdx !== -1) {
        try { meta = JSON.parse(full.slice(full.indexOf(META_MARKER) + META_MARKER.length)); } catch { /* malformed trailer — show text as-is */ }
      }
      setMsgs(prev => prev.map(m => m._id === mentorId ? { ...m, text: visibleFinal, activeTools: [], label: meta?.mode ? String(meta.mode).toUpperCase() : undefined } : m));
      setSuggestions(Array.isArray(meta?.suggestions) ? meta.suggestions : []);
      return true;
    } catch {
      // Network error or an empty stream body — same "never confirmed
      // persisted" situation as the pre-flight rejection above, so drop the
      // optimistic bubble here too rather than leaving a phantom sent message.
      setMsgs(prev => [
        ...prev.filter(m => m._id !== userId && m._id !== mentorId),
        { who: 'mentor', text: "I'm having trouble — try again in a moment.", _id: 'err' + Date.now() },
      ]);
      return false;
    } finally {
      setBusy(false);
    }
  }, [topicId]);

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
        `- Mode: topic`,
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
  }, [topicId, exporting]);

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
          {/* ponytail: voice (tone) selector hidden per request — remove `false &&` to re-enable; components/state kept intact. */}
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
          {displayMsgs.map((m, i) =>
            m.who === 'session-end'
              ? <div key={m._id || i} className="session-divider" role="separator">
                  <span className="session-divider-label">{formatSessionEndLabel(m.text)}</span>
                </div>
              : m.who === 'summary'
              ? <SummaryBlockIndicator key={m._id || i} summaryBlock={m.summaryBlock!} />
              : m.who === 'mentor' && !m.text
              // Empty mentor text is only ever legitimate for the in-flight
              // streaming placeholder (last message, still busy) — the
              // Typing indicator covers that case below. A *settled* empty
              // mentor message (historical bad data, or any future bug that
              // appends one) must still show something instead of silently
              // vanishing with no bubble, no error, no trace.
              ? (busy && i === displayMsgs.length - 1
                  ? null
                  : <Bubble key={m._id || i} who="mentor" item={{ ...m, text: '(no reply recorded)' }} />)
              : m.who === 'verdict'
              ? <VerdictMsg key={m._id || i} item={m as any} />
              : m.who === 'system'
              ? <div key={m._id || i} className="system-msg">
                  <span className="system-msg-text">{m.text}</span>
                </div>
              : m.who === 'mentor' && looksLikeQuestion(m.text)
              ? <MentorQuestionCard key={m._id || i} text={m.text} label={m.label} timestamp={m.timestamp} />
              : <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />
          )}
          {busy && (() => {
            const last = msgs[msgs.length - 1];
            const activeTools = last?.who === 'mentor' ? last.activeTools : undefined;
            if (activeTools && activeTools.length > 0) {
              const label = activeTools.map(t => TOOL_LABELS[t] ?? t).join(' · ');
              return <ToolActivity label={label} />;
            }
            if (!(last?.who === 'mentor' && last?.text)) {
              return <Typing label="Thinking, may check the web for current info…" />;
            }
            return null;
          })()}

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
        tone={tone}
        onSend={send}
        busy={busy}
      />
    </div>
    <TopicContextPanel topicId={topicId} />
    </>
  );
}
