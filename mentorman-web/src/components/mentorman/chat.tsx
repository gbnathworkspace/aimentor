'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Icon } from './icons';
import { Bubble, VerdictMsg, Typing } from './ui';
import { MODES, TONES, type MessageItem, type ModeId, type ToneId, type Topic } from './data';
import { OnboardingBanner } from './OnboardingBanner';
import { TopicCreation, TopicRenameInput } from './TopicCreation';
import { SummaryBlockIndicator } from './SummaryBlockIndicator';
import { MentorQuestionCard, QuickReplyOptions, looksLikeQuestion, type QuickReplyOption } from './QuestionCard';
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

  const submit = () => {
    const t = val.trim();
    if (!t || busy || disabled) return;
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

export function ChatPanel({ topicId, mode, setMode, tone, setTone, onNav, onTopicUpdated, onTopicCreated, topics = [], profile, onStartDeferredOnboarding }: {
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
  onStartDeferredOnboarding?: () => void;
}) {
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<QuickReplyOption[]>([]);
  const [topicTitle, setTopicTitle] = useState<string>('New Topic');
  const bodyRef = useRef<HTMLDivElement>(null);
  const greetedRef = useRef(false);

  // Load messages when topicId changes
  useEffect(() => {
    if (!topicId) {
      setMsgs([]);
      setTopicTitle('New Topic');
      greetedRef.current = false;
      return;
    }
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
      .finally(() => { if (!cancelled) setBusy(false); });

    return () => { cancelled = true; };
  }, [topicId]);

  // Auto-scroll on new messages
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

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

  // Export the full topic transcript (all messages, not just the loaded page)
  // as a local .md file for offline analysis.
  const [exporting, setExporting] = useState(false);
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

  // If no topicId, show topic creation screen
  if (!topicId) {
    return (
      <div className="panel">
        <div className="panel-head">
          <div className="ph-left">
            <div className="ph-title">New Topic</div>
            <div className="ph-sub">create a topic to start chatting</div>
          </div>
        </div>
        <div className="chat-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <TopicCreation
            onTopicCreated={(id) => { onTopicCreated?.(id); }}
            onCancel={() => {}}
          />
        </div>
      </div>
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
          <div className="ph-sub">topic · {mode}</div>
        </div>
        <div className="ph-right">
          <ModeBar mode={mode} onMode={setMode} locked={msgs.some(m => m.who === 'user')} />
          <ToneBar tone={tone} onTone={setTone} />
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
          {busy && !(msgs[msgs.length - 1]?.who === 'mentor' && msgs[msgs.length - 1]?.text) && <Typing />}
        </div>
      </div>

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

      <Composer
        mode={mode}
        tone={tone}
        onSend={send}
        busy={busy}
      />
    </div>
  );
}
