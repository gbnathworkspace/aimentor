'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Icon } from './icons';
import { relativeTime } from '../../lib/topics/relativeTime';
import type { TopicListItem } from '../../lib/topics/types';

type IconName = 'spark' | 'code' | 'target' | 'chart';

type Suggestion = { icon: IconName; title: string; desc: string; prompt: string };

/** Starter prompts. Clicking one loads it into the composer rather than sending
 *  it outright — the prompts are open-ended because the selected topic supplies
 *  the subject. */
const SUGGESTIONS: Suggestion[] = [
  { icon: 'spark', title: 'Explain a concept', desc: 'Break down a topic step by step', prompt: 'Explain ' },
  { icon: 'code', title: 'Review my code', desc: 'Get feedback on what you wrote', prompt: 'Review my code for ' },
  { icon: 'target', title: 'Quiz me', desc: 'Test what you have learned', prompt: 'Quiz me on ' },
  { icon: 'chart', title: 'See my progress', desc: 'Review your skill graph', prompt: 'Show me my progress in ' },
];

/** Chosen destination: an existing topic, or a new one derived from the message. */
type Pick = { id: string | null; title: string };

const NEW_TOPIC: Pick = { id: null, title: 'New topic' };

export interface WelcomeScreenProps {
  /** Display name for the greeting; falls back to a plain "Welcome" when absent. */
  userName?: string;
  /** True while the topic is being created — locks the composer. */
  busy?: boolean;
  error?: string | null;
  /** Sends `text` to the chosen topic, or opens a new one when topicId is null. */
  onStart: (text: string, topicId: string | null) => void;
  onNav: (view: string) => void;
}

/**
 * The chat panel's empty state: a greeting, a topic picker, a composer, and four
 * starter prompts.
 *
 * The picker is optional. Send without choosing and the message is routed
 * against your existing topics by a Haiku call (app/services/topic_router.py):
 * a hit offers to continue that thread, a miss opens a new topic titled from
 * the message (so there's no naming step). Choosing from the picker skips
 * the routing call entirely.
 */
export function WelcomeScreen({ userName, busy, error, onStart, onNav }: WelcomeScreenProps) {
  const [text, setText] = useState('');
  const [focus, setFocus] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  // null = the user hasn't chosen, so submitting routes to a topic first.
  const [picked, setPicked] = useState<Pick | null>(null);
  const [detected, setDetected] = useState<TopicListItem | null>(null);
  // Set when the router can't confidently pick one topic but found a few
  // plausible ones (up to 4) — a short pick-list instead of a single guess.
  const [ambiguous, setAmbiguous] = useState<TopicListItem[] | null>(null);
  const [routing, setRouting] = useState(false);
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch('/api/topics')
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => { if (Array.isArray(data)) setTopics(data); })
      .catch(() => {});
  }, []);

  const canSend = text.trim().length > 0 && !busy && !routing;

  const submit = async () => {
    if (!canSend) return;
    const body = text.trim();
    if (picked) {
      onStart(body, picked.id);
      return;
    }
    // No explicit choice — offer the topic this sounds like before opening a
    // new one, so related work doesn't scatter across duplicate topics.
    setRouting(true);
    try {
      const res = await fetch('/api/topics/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: body }),
      });
      const data = res.ok ? await res.json() : null;
      const match = data?.topicId ? topics.find((t) => t.topicId === data.topicId) : null;
      if (match) {
        setDetected(match);
        return;
      }
      const candidateIds: string[] = Array.isArray(data?.candidates)
        ? data.candidates.map((c: { topicId: string }) => c.topicId)
        : [];
      const candidates = candidateIds
        .map((id) => topics.find((t) => t.topicId === id))
        .filter((t): t is TopicListItem => !!t);
      if (candidates.length > 0) {
        setAmbiguous(candidates);
        return;
      }
    } catch {
      // Fail open to a new topic — same behavior as a genuine "no match".
    } finally {
      setRouting(false);
    }
    onStart(body, null);
  };

  const choose = (p: Pick) => {
    setPicked(p);
    setMenuOpen(false);
    setDetected(null);
    setAmbiguous(null);
    ref.current?.focus();
  };

  const pickSuggestion = (s: Suggestion) => {
    setText(s.prompt);
    setFocus(true);
    // Focus after the value lands so the caret can be parked at the end — the
    // prompts are prefixes the user is meant to finish.
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    });
  };

  return (
    <div className="panel">
      <div className="panel-head" style={{ justifyContent: 'flex-end' }}>
        <div className="ph-right">
          <button
            className="btn btn-sm btn-ghost"
            type="button"
            style={{ whiteSpace: 'nowrap' }}
            onClick={() => { setText(''); setDetected(null); setAmbiguous(null); setPicked(NEW_TOPIC); ref.current?.focus(); }}
          >
            <Icon name="edit" size={13} /> New Topic
          </button>
          <button
            className="icon-btn"
            type="button"
            title="Settings"
            aria-label="Settings"
            onClick={() => onNav('settings')}
          >
            <Icon name="gear" size={16} />
          </button>
        </div>
      </div>

      <div className="welcome-wrap">
        <div className="welcome-inner">
          <div className="welcome-hero">
            <span className="welcome-spark"><Icon name="spark" size={34} /></span>
            <h1 className="welcome-title">{userName ? `Welcome, ${userName}` : 'Welcome'}</h1>
          </div>

          <div className={`composer-box ${focus ? 'focus' : ''}`} style={{ width: '100%', padding: '14px 16px 12px' }}>
            <div style={{ position: 'relative', display: 'inline-block', marginBottom: 10 }}>
              <button
                className="pill ok topic-pick"
                type="button"
                disabled={busy}
                title="Continue an existing topic, or leave as New topic"
                aria-haspopup="listbox"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((o) => !o)}
              >
                <span className="ind" />
                {picked ? picked.title : 'Choose a topic'}
                <Icon name="chevronDown" size={12} />
              </button>

              {menuOpen && (
                <>
                  {/* Click-away catcher — cheaper than a document listener. */}
                  <div onClick={() => setMenuOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 19 }} />
                  <div
                    className="onb-options topic-menu"
                    role="listbox"
                    aria-label="Choose a topic"
                  >
                    <div className="topic-menu-head">Choose a topic to continue</div>
                    <button type="button" role="option" aria-selected={picked?.id === null} className="onb-option onb-option-custom" onClick={() => choose(NEW_TOPIC)}>
                      <span className="onb-option-num onb-option-num-custom"><Icon name="plus" size={10} /></span>
                      <span className="onb-option-title">New topic</span>
                    </button>
                    {topics.map((t) => (
                      <button
                        key={t.topicId}
                        type="button"
                        role="option"
                        aria-selected={picked?.id === t.topicId}
                        className="onb-option"
                        title={t.title}
                        onClick={() => choose({ id: t.topicId, title: t.title })}
                      >
                        <span className="onb-option-title">{t.title}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
            <textarea
              ref={ref}
              rows={2}
              value={text}
              disabled={busy}
              placeholder="How can I help you today?"
              aria-label="What would you like to learn?"
              style={{ minHeight: 46 }}
              onFocus={() => setFocus(true)}
              onBlur={() => setFocus(false)}
              onChange={(e) => { setText(e.target.value); setDetected(null); setAmbiguous(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
            />
            <div className="composer-tools">
              {/* Attach and upload both need a session id, which does not exist
                  until the topic is created — shown but inert so the toolbar
                  doesn't shift when the real composer takes over. */}
              <button className="tool-btn" type="button" disabled title="Start a topic first to attach documents">
                <Icon name="plus" size={15} />
              </button>
              <button className="tool-btn" type="button" disabled title="Start a topic first to upload notes">
                <Icon name="upload" size={14} />
              </button>
              <div className="spacer" />
              <button
                className="send-btn"
                type="button"
                onClick={submit}
                disabled={!canSend}
                title={busy ? 'Starting…' : routing ? 'Finding the right topic…' : 'Send'}
                aria-label="Send"
              >
                <Icon name="arrowUp" size={16} />
              </button>
            </div>
          </div>

          <div className="welcome-suggestions">
            {SUGGESTIONS.map((s) => (
              <button
                key={s.title}
                type="button"
                className="welcome-suggestion"
                disabled={busy}
                onClick={() => pickSuggestion(s)}
              >
                <span className="ws-icon"><Icon name={s.icon} size={15} /></span>
                <span style={{ minWidth: 0 }}>
                  <span className="ws-title">{s.title}</span>
                  <span className="ws-desc">{s.desc}</span>
                </span>
              </button>
            ))}
          </div>

          {error && <div className="welcome-error" role="alert">{error}</div>}

          <div className="welcome-foot">
            MentorMan learns with you — pick up a topic or start something new
          </div>
        </div>
      </div>

      {detected && (
        <div className="skip-dialog-overlay" onClick={() => setDetected(null)}>
          <div className="skip-dialog welcome-route" onClick={(e) => e.stopPropagation()}>
            <div className="onb-card-icon" style={{ marginBottom: 10 }}><Icon name="target" size={15} /></div>
            <div className="skip-dialog-title">
              Sounds like <span style={{ color: 'var(--accent)' }}>{detected.title}</span>
            </div>
            <div className="skip-dialog-desc">
              You have an existing chat here — last active {relativeTime(detected.lastActiveAt)}.
            </div>
            <div className="welcome-route-actions">
              <button type="button" className="btn btn-accent btn-sm" onClick={() => onStart(text.trim(), detected.topicId)}>
                Continue this chat
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onStart(text.trim(), null)}>
                Start a new topic instead
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setDetected(null); setMenuOpen(true); }}>
                Not this — pick a different topic
              </button>
            </div>
          </div>
        </div>
      )}

      {ambiguous && (
        <div className="skip-dialog-overlay" onClick={() => setAmbiguous(null)}>
          <div className="skip-dialog welcome-route" onClick={(e) => e.stopPropagation()}>
            <div className="onb-card-icon" style={{ marginBottom: 10 }}><Icon name="target" size={15} /></div>
            <div className="skip-dialog-title">Which topic is this?</div>
            <div className="skip-dialog-desc">
              A few of your chats could fit — pick one to continue it, or start something new.
            </div>
            <div className="welcome-route-actions welcome-route-actions-list">
              {ambiguous.map((t) => (
                <button
                  key={t.topicId}
                  type="button"
                  className="btn btn-ghost btn-sm welcome-route-candidate"
                  onClick={() => onStart(text.trim(), t.topicId)}
                >
                  {t.title}
                </button>
              ))}
              <button type="button" className="btn btn-accent btn-sm" onClick={() => onStart(text.trim(), null)}>
                None of these — start a new topic
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
