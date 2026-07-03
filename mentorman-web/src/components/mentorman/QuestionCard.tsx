'use client';

import React from 'react';
import { Icon } from './icons';
import { fmt } from './ui';
import { SpeakButton } from './SpeakButton';

export type QuickReplyOption = { title: string; description: string };

/** Detects whether an assistant message is asking a question worth rendering
 *  as a question card, rather than a plain chat bubble. */
export function looksLikeQuestion(text: string): boolean {
  return text.trim().endsWith('?');
}

/** Renders a mentor turn as a question card: icon badge, bold heading, supporting text.
 *  The LLM is prompted to lead with "question\n\ncontext" — split on the first blank
 *  line; if there isn't one, the whole message is the heading. */
export function MentorQuestionCard({ text }: { text: string }) {
  const idx = text.indexOf('\n\n');
  const heading = (idx === -1 ? text : text.slice(0, idx)).replace(/\*\*/g, '').trim();
  const body = idx === -1 ? null : text.slice(idx + 2).trim();
  return (
    <div className="onb-card fade-up">
      <div className="onb-card-icon"><Icon name="spark" size={14} /></div>
      <div className="onb-card-body">
        <div className="onb-card-heading">{heading}</div>
        {body && <div className="onb-card-desc">{fmt(body)}</div>}
      </div>
      <SpeakButton text={text} className="onb-card-speak" />
    </div>
  );
}

/** The tappable option rows below a question card. Always ends with a
 *  "type your own answer" row (the free-text equivalent of AskUserQuestion's
 *  "Other") so a discrete option list never forecloses an open-ended reply. */
export function QuickReplyOptions({
  options, onSelect, onTypeOwn,
}: {
  options: QuickReplyOption[];
  onSelect: (title: string) => void;
  onTypeOwn: () => void;
}) {
  return (
    <div className="onb-options">
      {options.map(s => (
        <button key={s.title} className="onb-option" onClick={() => onSelect(s.title)}>
          <span className="onb-option-text">
            <span className="onb-option-title">{s.title}</span>
            <span className="onb-option-desc">{s.description}</span>
          </span>
          <Icon name="arrowR" size={16} />
        </button>
      ))}
      <button className="onb-option onb-option-custom" onClick={onTypeOwn}>
        <span className="onb-option-text">
          <span className="onb-option-title">Type your own answer</span>
          <span className="onb-option-desc">None of these fit — write a custom reply.</span>
        </span>
        <Icon name="arrowR" size={16} />
      </button>
    </div>
  );
}
