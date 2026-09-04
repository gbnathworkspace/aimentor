'use client';

import React, { useState } from 'react';
import { Icon } from './icons';
import { fmt, ModeBadge, formatBubbleTime } from './ui';
import { SpeakButton } from './SpeakButton';

export type QuickReplyOption = { title: string; description: string };

/** Detects whether an assistant message is asking a question worth rendering
 *  as a question card, rather than a plain chat bubble. Checks the first
 *  paragraph specifically (not the whole message) because that's the part
 *  MentorQuestionCard renders as its heading — a message ending in "?" after
 *  a non-question intro paragraph would otherwise get misrendered as a card
 *  with a non-question heading. */
export function looksLikeQuestion(text: string): boolean {
  const idx = text.indexOf('\n\n');
  const firstPara = idx === -1 ? text : text.slice(0, idx);
  return firstPara.trim().replace(/\*\*/g, '').endsWith('?');
}

/** Renders a mentor turn as a question card: icon badge, bold heading, supporting text.
 *  The LLM is prompted to lead with "question\n\ncontext" — split on the first blank
 *  line; if there isn't one, the whole message is the heading. */
export function MentorQuestionCard({ text, label, timestamp }: { text: string; label?: string; timestamp?: string }) {
  const idx = text.indexOf('\n\n');
  const heading = (idx === -1 ? text : text.slice(0, idx)).replace(/\*\*/g, '').trim();
  const body = idx === -1 ? null : text.slice(idx + 2).trim();
  const time = timestamp && formatBubbleTime(timestamp);
  return (
    // Same hover/focus-reveal timestamp as Bubble (see ui.tsx) — question
    // cards are a separate render path for mentor turns, so the feature has
    // to be wired here too, not just on the default bubble.
    <div className="bubble-row" tabIndex={time ? 0 : undefined}>
      {time && <span className="bubble-time">{time}</span>}
      <div className="onb-card fade-up">
        <div className="onb-card-icon"><Icon name="spark" size={14} /></div>
        <div className="onb-card-body">
          {label && <ModeBadge label={label} />}
          <div className="onb-card-heading">{heading}</div>
          {body && <div className="onb-card-desc">{fmt(body)}</div>}
        </div>
        <SpeakButton text={text} className="onb-card-speak" />
      </div>
    </div>
  );
}

/** The tappable option rows below a question card, presented as one bordered
 *  card with numbered rows (matching Claude Code's own AskUserQuestion card).
 *  Always ends with a "type your own answer" row (the free-text equivalent of
 *  AskUserQuestion's "Other") so a discrete option list never forecloses an
 *  open-ended reply. A close button lets the user dismiss the whole card
 *  without picking one, and a separate collapse toggle lets them shrink the
 *  card down to a low-height header (keeping the suggestions, just out of
 *  the way of the message underneath) without losing them the way close does. */
export function QuickReplyOptions({
  options, onSelect, onTypeOwn, onClose,
}: {
  options: QuickReplyOption[];
  onSelect: (title: string) => void;
  onTypeOwn: () => void;
  onClose: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className="onb-options">
      <button
        className="onb-options-toggle"
        title={collapsed ? 'Expand suggestions' : 'Collapse suggestions'}
        aria-label={collapsed ? 'Expand suggestions' : 'Collapse suggestions'}
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((v) => !v)}
      >
        <Icon name="chevronDown" size={12} style={{ transform: collapsed ? 'rotate(-90deg)' : undefined, transition: 'transform .14s' }} />
      </button>
      <button className="onb-options-close" title="Dismiss suggestions" aria-label="Dismiss suggestions" onClick={onClose}>
        <Icon name="x" size={12} />
      </button>
      {collapsed ? (
        <div className="onb-options-summary">{options.length} suggestion{options.length !== 1 ? 's' : ''}</div>
      ) : (
        <>
          {options.map((s, i) => (
            <button key={s.title} className="onb-option" title={s.description} onClick={() => onSelect(s.title)}>
              <span className="onb-option-num">{i + 1}</span>
              <span className="onb-option-title">{s.title}</span>
              <span className="onb-option-arrow"><Icon name="arrowR" size={12} /></span>
            </button>
          ))}
          <button className="onb-option onb-option-custom" title="None of these fit — write a custom reply." onClick={onTypeOwn}>
            <span className="onb-option-num onb-option-num-custom"><Icon name="edit" size={10} /></span>
            <span className="onb-option-title">Type your own answer</span>
            <span className="onb-option-arrow"><Icon name="arrowR" size={12} /></span>
          </button>
        </>
      )}
    </div>
  );
}
