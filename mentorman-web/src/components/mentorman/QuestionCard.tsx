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

/** One MCQ in the fixed quiz template (.kiro/specs/mcq-quiz Req 1). */
export type Quiz = {
  q: number;
  of: number;
  /** Scoring/summary only — not shown on the card (Decision 8). */
  subtopic?: string;
  stem: string;
  code?: string;
  options: { id: string; text: string }[];
  answer: string;
  why: string;
  misconceptions?: Record<string, string>;
  /** Option id, "skip" for "I don't know", or absent while unanswered. */
  picked?: string;
};

/** Finish-turn score card data, computed server-side from the graded picks (Req 6). */
export type QuizSummary = {
  correct: number;
  total: number;
  subtopics: { subtopic: string; mastery: number }[];
  missed: {
    q: number; stem: string; picked?: string; pickedText: string;
    answer: string; answerText: string; misconception: string; why: string;
  }[];
  weakest?: string | null;
};

/** Minimal on-brand quiz card (Decisions 4, 8-10): `q / of`, stem, code,
 *  vertical options. Grades the pick locally — no LLM call. */
export function QuizCard({ quiz, onAnswer, onExplain }: {
  quiz: Quiz;
  onAnswer?: (picked: string) => void;
  onExplain?: () => void;
}) {
  const picked = quiz.picked ?? undefined;
  const answered = picked !== undefined;
  const right = picked === quiz.answer;
  const mistake = answered && !right && picked !== 'skip' ? quiz.misconceptions?.[picked!] : undefined;
  return (
    <div className="bubble-row">
      <div className="onb-card quiz-card fade-up">
        <div className="onb-card-icon"><Icon name="spark" size={14} /></div>
        <div className="onb-card-body quiz-body">
          <div className="quiz-count">{quiz.q} / {quiz.of}</div>
          <div className="quiz-stem">{fmt(quiz.stem)}</div>
          {quiz.code && <pre className="quiz-code"><code>{quiz.code}</code></pre>}
          <div className="quiz-options" role="radiogroup" aria-label={`Question ${quiz.q} options`}>
            {quiz.options.map((o) => {
              const state = !answered ? '' : o.id === quiz.answer ? 'correct' : o.id === picked ? 'wrong' : 'dim';
              return (
                <button
                  key={o.id}
                  type="button"
                  role="radio"
                  aria-checked={picked === o.id}
                  className={`quiz-option ${state}`}
                  disabled={answered || !onAnswer}
                  onClick={() => onAnswer?.(o.id)}
                >
                  <span className="quiz-option-id">{o.id}</span>
                  <span className="quiz-option-text">{o.text}</span>
                  {state === 'correct' && <Icon name="check" size={13} />}
                  {state === 'wrong' && <Icon name="x" size={13} />}
                </button>
              );
            })}
          </div>
          {!answered ? (
            <button type="button" className="quiz-link quiz-skip" disabled={!onAnswer} onClick={() => onAnswer?.('skip')}>
              I don't know
            </button>
          ) : (
            <div className="quiz-result" role="status">
              <div className={`quiz-verdict ${right ? 'correct' : 'wrong'}`}>
                <Icon name={right ? 'check' : 'x'} size={13} />
                {right ? `${quiz.answer} — Correct` : `${quiz.answer} is the answer`}
              </div>
              {mistake && <div className="quiz-why"><span className="quiz-why-label">Your pick:</span> {fmt(mistake)}</div>}
              <div className="quiz-why">{fmt(quiz.why)}</div>
              {onExplain && (
                <button type="button" className="quiz-link" onClick={onExplain}>Explain more</button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** End-of-quiz card (Req 6): score, per-subtopic bars, missed-question review,
 *  and a "Teach me what I missed" action. Numbers come from code, not the model. */
export function QuizSummaryCard({ summary, note, onTeach }: {
  summary: QuizSummary;
  /** The mentor's one-line pointer, if any. */
  note?: string;
  onTeach?: () => void;
}) {
  return (
    <div className="bubble-row">
      <div className="onb-card quiz-card fade-up">
        <div className="onb-card-icon"><Icon name="chart" size={14} /></div>
        <div className="onb-card-body quiz-body">
          <div className="quiz-count">Quiz complete</div>
          <div className="quiz-score">{summary.correct} / {summary.total}</div>
          <div className="quiz-bars">
            {summary.subtopics.map((s) => (
              <div key={s.subtopic} className="quiz-bar-row">
                <span className="quiz-bar-label" title={s.subtopic}>{s.subtopic}</span>
                <span className="quiz-bar-track" role="img" aria-label={`${s.subtopic}: ${s.mastery}%`}>
                  <span className="quiz-bar-fill" style={{ width: `${s.mastery}%` }} />
                </span>
                <span className="quiz-bar-pct">{s.mastery}%</span>
              </div>
            ))}
          </div>
          {summary.missed.length > 0 && (
            <div className="quiz-review">
              <div className="quiz-review-head">Review</div>
              {summary.missed.map((m) => (
                <div key={m.q} className="quiz-review-item">
                  <div className="quiz-review-stem">{m.q}. {fmt(m.stem)}</div>
                  <div className="quiz-why">
                    <Icon name="x" size={11} /> {m.picked && m.picked !== 'skip' ? `${m.picked}: ${m.pickedText}` : "You didn't know"}
                    {m.misconception && <> — {m.misconception}</>}
                  </div>
                  <div className="quiz-why"><Icon name="check" size={11} /> {m.answer}: {m.answerText}</div>
                </div>
              ))}
            </div>
          )}
          {note && <div className="quiz-why quiz-note">{fmt(note)}</div>}
          {onTeach && summary.missed.length > 0 && (
            <button type="button" className="btn btn-accent btn-sm quiz-teach" onClick={onTeach}>
              Teach me what I missed <Icon name="arrowR" size={12} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
