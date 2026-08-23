import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './icons';
import type { CoreProfile } from '@/lib/mentorman-api';

interface WeightFlag {
  subtopic: string;
  baseline: number;
  final: number;
  delta: number;
}

interface WeightsResponse {
  subtopics: string[];
  weights: Record<string, number> | null;
  flags: WeightFlag[];
  needsPairwise: boolean;
}

type Phase = 'setup' | 'loading' | 'result' | 'error';

const TEMP_MIN = 0.25;
const TEMP_MAX = 3;
const TEMP_DEFAULT = 1;

// Plain-language stand-in for the raw temperature value — nobody needs to
// see "1.35", they need to know which way the slider is leaning.
function temperatureLabel(t: number): string {
  if (t <= 0.5) return 'Very focused';
  if (t < 0.9) return 'Focused';
  if (t <= 1.1) return 'Balanced';
  if (t < 2) return 'Flatter';
  return 'Very even';
}

// Reshapes the computed weights by a single global "temperature" instead of
// per-subtopic nudges: T<1 sharpens the distribution (biggest weight grows,
// smallest shrinks toward 0), T>1 flattens it toward uniform. T=1 is a no-op.
function applyTemperature(baseline: Record<string, number>, temperature: number): Record<string, number> {
  const powered: Record<string, number> = {};
  for (const k of Object.keys(baseline)) {
    powered[k] = Math.pow(Math.max(baseline[k], 0) / 100, 1 / temperature);
  }
  const total = Object.values(powered).reduce((a, b) => a + b, 0);
  const result: Record<string, number> = {};
  for (const k of Object.keys(powered)) {
    result[k] = total === 0 ? 100 / Object.keys(powered).length : (powered[k] / total) * 100;
  }
  return result;
}

function equalSplit(subtopics: string[]): Record<string, number> {
  const n = subtopics.length || 1;
  const w: Record<string, number> = {};
  for (const s of subtopics) w[s] = 100 / n;
  return w;
}

// Full round-robin: rank 0 beats everyone below it, rank 1 beats everyone
// below it, etc. — turns a drag-free reorder into pairwise (winner, loser)
// comparisons, the AHP-lite fallback the backend expects.
function rankingToComparisons(order: string[]): [string, string][] {
  const pairs: [string, string][] = [];
  for (let i = 0; i < order.length; i++) {
    for (let j = i + 1; j < order.length; j++) pairs.push([order[i], order[j]]);
  }
  return pairs;
}

interface GoalCard {
  key: string;
  title: string;
  tag: string;
  /** Omitted where the title already says everything — repeating a generic line
   *  on every card is noise, not information. */
  description?: string;
  /** Stated goal sent as `goalIntent` — scored by relevance server-side. Cards
   *  can't go through the work_evidence path: one line of intent has nothing to
   *  mention-count, so it always reads as sparse and collapses to equal split. */
  intent: string;
  /** True for cards built from the profile, filtered through classify_relevance's
   *  scoped L1 memory (l1Scope) — shows a badge so it's visually distinct from
   *  "Just revising"/"Something else", which aren't L1-derived. */
  fromL1Scope?: boolean;
}

const CONTEXT_TAGS: Record<string, string> = {
  job_interview: 'INTERVIEW',
  high_stakes_exam: 'EXAM',
  competitive_test: 'TEST',
};

function humanize(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const STOPWORDS = new Set(['and', 'or', 'the', 'for', 'with', 'into', 'from', 'its']);

function keyTokens(s: string): Set<string> {
  return new Set(
    s.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/)
      .filter((w) => w.length > 2 && !STOPWORDS.has(w))
  );
}

// L1 focus areas are free text appended over time, so near-restatements pile up
// ("REST API development and system design" vs "REST API design and scalability").
// Showing both as separate goals is just noise — keep the first, drop the echo.
export function isNearDuplicate(a: string, b: string): boolean {
  const ta = keyTokens(a);
  const tb = keyTokens(b);
  if (ta.size === 0 || tb.size === 0) return false;
  let shared = 0;
  for (const t of ta) if (tb.has(t)) shared += 1;
  return shared / Math.min(ta.size, tb.size) >= 0.6;
}

// Suggests quick-pick goals from the user's existing L1 profile (focus areas,
// learning context) instead of making them type evidence from scratch every
// time — "Something else" (rendered separately, not a GoalCard) is the escape
// hatch back to pasting specific work evidence.
//
// Focus areas are profile-wide, not topic-scoped, so they may only partly
// overlap the topic being weighted — classify_relevance judges the actual
// overlap (see .kiro/specs/topic-scoping), and `l1Scope` here is that
// judgment's cached output: any focus area / context label it marked
// "irrelevant" to this topic is dropped from the picker entirely rather
// than offered as a goal that doesn't apply. Entries with no verdict yet
// (l1Scope empty/absent) or judged "uncertain"/"relevant" are kept —
// callers are expected to resolve "uncertain" ones before this runs (see
// chat.tsx's openWeights gate).
export function buildGoalCards(
  profile: CoreProfile | null | undefined,
  topicTitle: string,
  l1Scope?: { situation: string; verdict: string }[] | null,
): GoalCard[] {
  const cards: GoalCard[] = [];
  const verdictBySituation = new Map((l1Scope ?? []).map((e) => [e.situation, e.verdict]));
  const irrelevant = new Set(
    (l1Scope ?? []).filter((e) => e.verdict === 'irrelevant').map((e) => e.situation)
  );

  // classify_relevance's verdict ranks the survivors — a confirmed "relevant"
  // judgment goes first so the top card (the one auto-selected below) is the
  // one the classifier actually vouched for, not just whichever happened to
  // be first in the user's raw focus_areas list.
  const candidates = (profile?.focus_areas ?? []).filter((a) => !irrelevant.has(a));
  const ranked = [...candidates].sort((a, b) => {
    const score = (v?: string) => (v === 'relevant' ? 0 : v === undefined ? 1 : 2); // relevant, unjudged, uncertain
    return score(verdictBySituation.get(a)) - score(verdictBySituation.get(b));
  });

  const areas: string[] = [];
  for (const area of ranked) {
    if (areas.some((kept) => isNearDuplicate(kept, area))) continue;
    areas.push(area);
    if (areas.length === 2) break;
  }

  for (const area of areas) {
    cards.push({
      key: `focus:${area}`,
      title: area,
      tag: 'YOUR FOCUS',
      intent: `My current focus is: ${area}. Prioritize the parts of ${topicTitle} that genuinely support that work.`,
      fromL1Scope: true,
    });
  }

  const ctx = profile?.learning_context;
  if (ctx && ctx !== 'self_directed') {
    const label = profile?.learning_context_detail?.label || humanize(ctx);
    if (!irrelevant.has(label)) {
      cards.push({
        key: 'context',
        title: label,
        tag: CONTEXT_TAGS[ctx] ?? 'GOAL',
        description: 'Lean toward what usually comes up when preparing for this.',
        intent: `I'm preparing for: ${label}. Prioritize the parts of ${topicTitle} that typically matter most for that.`,
        fromL1Scope: true,
      });
    }
  }

  cards.push({
    key: 'revise',
    title: 'Just revising',
    tag: 'REFRESH',
    description: 'An even pass over everything — keep concepts sharp.',
    intent: 'A general refresher with no specific goal — treat every subtopic as roughly equally worth revisiting.',
  });

  return cards;
}

export interface SubtopicWeightsModalProps {
  open: boolean;
  onClose: () => void;
  topicId?: string | null;
  topicTitle?: string;
  profile?: CoreProfile | null;
  /** The topic's l1_scope — filters out focus areas/context judged
   *  irrelevant to this topic. Omit or pass [] to show every card unfiltered. */
  l1Scope?: { situation: string; verdict: string }[] | null;
}

export function SubtopicWeightsModal({ open, onClose, topicId, topicTitle, profile, l1Scope }: SubtopicWeightsModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  const [phase, setPhase] = useState<Phase>('setup');
  const [workEvidence, setWorkEvidence] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  // 'custom' selects the free-text fallback; any other value is a GoalCard key.
  const [selectedGoal, setSelectedGoal] = useState<string | null>(null);

  const goalCards = useMemo(
    () => buildGoalCards(profile, topicTitle || 'this topic', l1Scope),
    [profile, topicTitle, l1Scope]
  );

  // 'custom' is just another option in the same radiogroup — keeping it in the
  // list (rather than rendered separately) is what makes arrow-key nav uniform.
  const options: GoalCard[] = useMemo(
    () => [
      ...goalCards,
      {
        key: 'custom',
        title: 'Something else',
        tag: 'CUSTOM',
        description: "Paste recent commits, tickets, or PR comments and we'll go from there.",
        intent: '',
      },
    ],
    [goalCards]
  );

  const hasFocusCards = goalCards.some((c) => c.key.startsWith('focus:'));
  const goalRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onGoalKeyDown = (e: React.KeyboardEvent, key: string) => {
    const idx = options.findIndex((o) => o.key === key);
    let next: number;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') next = (idx + 1) % options.length;
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') next = (idx - 1 + options.length) % options.length;
    else return;
    e.preventDefault();
    const nextKey = options[next].key;
    setSelectedGoal(nextKey);
    goalRefs.current[nextKey]?.focus();
  };

  const [baseline, setBaseline] = useState<Record<string, number>>({});
  const [temperature, setTemperature] = useState(TEMP_DEFAULT);
  const [editing, setEditing] = useState(false);
  // Manual reorder-to-rank, offered inside Edit as an alternative to the
  // temperature control — not a forced step. Evidence too sparse to count
  // reliably just falls back to an equal split instead of blocking the view.
  const [rankMode, setRankMode] = useState(false);
  const [rankOrder, setRankOrder] = useState<string[]>([]);
  const [order, setOrder] = useState<string[]>([]); // fixed at result time — editing must not reshuffle rows

  const display = useMemo(() => applyTemperature(baseline, temperature), [baseline, temperature]);

  const reset = useCallback(() => {
    setPhase('setup');
    setErrorMsg('');
    setTemperature(TEMP_DEFAULT);
    setEditing(false);
    setRankMode(false);
    setSelectedGoal(null);
    setWorkEvidence('');
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  }, [onClose]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
    else reset();
  }, [open, reset]);

  // Auto-select the top classify_relevance-ranked card so opening the modal
  // is a confirm-or-change decision, not a blank pick — goalCards[0] is
  // always defined (falls back to "Just revising" when nothing else
  // qualifies), so this never lands on "custom".
  useEffect(() => {
    if (open && selectedGoal === null && goalCards[0]) {
      setSelectedGoal(goalCards[0].key);
    }
  }, [open, goalCards, selectedGoal]);

  const runQuery = useCallback(async (
    pairwiseComparisons?: [string, string][],
    source?: { evidence?: string; intent?: string },
  ) => {
    if (!topicId) return;
    const evidence = source?.intent ? undefined : (source?.evidence ?? workEvidence);
    setPhase('loading');
    setErrorMsg('');
    try {
      const res = await fetch(`/api/topic/${topicId}/subtopic-weights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: 'job_performance',
          workEvidence: evidence?.trim() || undefined,
          goalIntent: source?.intent,
          pairwiseComparisons,
        }),
      });
      const data: WeightsResponse & { detail?: string } = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || 'Could not derive weights.');
        setPhase('error');
        return;
      }
      // Sparse evidence: fall back to an equal split rather than forcing the
      // user through a ranking step before they can see anything.
      const w = data.needsPairwise ? equalSplit(data.subtopics) : data.weights || {};
      setBaseline(w);
      setTemperature(TEMP_DEFAULT);
      setEditing(false);
      setRankMode(false);
      setOrder([...data.subtopics].sort((a, b) => (w[b] ?? 0) - (w[a] ?? 0)));
      setPhase('result');
    } catch {
      setErrorMsg('Request failed — try again.');
      setPhase('error');
    }
  }, [topicId, workEvidence]);

  const startPreparing = () => {
    if (selectedGoal === 'custom') {
      runQuery(undefined, { evidence: workEvidence });
      return;
    }
    const card = goalCards.find((c) => c.key === selectedGoal);
    if (!card) return;
    runQuery(undefined, { intent: card.intent });
  };

  const canStart = selectedGoal === 'custom' ? !!workEvidence.trim() : !!selectedGoal;

  const openRankMode = () => {
    setRankOrder(order);
    setRankMode(true);
  };

  const applyRanking = useCallback(() => {
    runQuery(rankingToComparisons(rankOrder));
  }, [rankOrder, runQuery]);

  const moveRank = (index: number, dir: -1 | 1) => {
    setRankOrder((prev) => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  if (!open) return null;

  return (
    <div className="sw-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className="sw-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sw-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="sw-head">
          <div>
            <h2 id="sw-title" className="sw-title">Where should you focus?</h2>
            <div className="sw-sub">{topicTitle ? `for ${topicTitle}` : 'Adjust your study focus'}</div>
          </div>
          <button className="icon-btn" title="Close" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        {phase === 'setup' && (
          <div className="sw-setup">
            <div className="sw-label" id="sw-goal-label">
              Confirm your goal <span className="sw-required">(required)</span>
            </div>
            {hasFocusCards && (
              <p className="sw-goal-note">
                We've pre-selected the focus area classify_relevance ranked highest for {topicTitle || 'this topic'} — change it below if that's not what you meant.
              </p>
            )}
            <div className="goal-card-list" role="radiogroup" aria-labelledby="sw-goal-label">
              {options.map((card, i) => {
                const checked = selectedGoal === card.key;
                return (
                  <button
                    key={card.key}
                    ref={(el) => { goalRefs.current[card.key] = el; }}
                    type="button"
                    role="radio"
                    aria-checked={checked}
                    tabIndex={checked || (!selectedGoal && i === 0) ? 0 : -1}
                    className={`goal-card${checked ? ' goal-card--active' : ''}`}
                    onClick={() => setSelectedGoal(card.key)}
                    onKeyDown={(e) => onGoalKeyDown(e, card.key)}
                  >
                    <span className={`goal-card-radio${checked ? ' goal-card-radio--active' : ''}`} />
                    <span className="goal-card-body">
                      <span className="goal-card-title-row">
                        {card.fromL1Scope && (
                          <span className="goal-card-l1-badge" title="From your scoped L1 memory — ranked relevant to this topic by classify_relevance">
                            <Icon name="target" size={11} />
                          </span>
                        )}
                        <span className="goal-card-title">{card.title}</span>
                        <span className="goal-card-tag">{card.tag}</span>
                      </span>
                      {card.description && <span className="goal-card-desc">{card.description}</span>}
                    </span>
                  </button>
                );
              })}
            </div>

            {selectedGoal === 'custom' && (
              <textarea
                id="sw-evidence"
                className="sw-textarea"
                style={{ marginTop: 10 }}
                placeholder="e.g. “Set up a CloudFront distribution in front of our API, debugged a cache invalidation issue, reviewed a PR adding signed cookies…”"
                value={workEvidence}
                onChange={(e) => setWorkEvidence(e.target.value)}
                rows={4}
                maxLength={20000}
                autoFocus
              />
            )}

            <div className="sw-goal-footer">
              <button
                className="btn btn-accent"
                disabled={!topicId || !canStart}
                onClick={startPreparing}
              >
                Start preparing →
              </button>
              {!canStart && (
                <span className="sw-goal-hint-text">
                  {selectedGoal === 'custom' ? 'Paste some evidence to continue' : 'Pick one to continue'}
                </span>
              )}
            </div>
          </div>
        )}

        {phase === 'loading' && (
          <div className="sw-status">Figuring out where to focus…</div>
        )}

        {phase === 'error' && (
          <div className="sw-status sw-status-error">
            {errorMsg}
            <button className="btn btn-ghost sw-back" onClick={reset}>Back</button>
          </div>
        )}

        {phase === 'result' && (
          <div className="sw-body">
            <div className="sw-hint">
              {rankMode
                ? 'Drag from most to least important — we\'ll work out the rest from your order.'
                : editing
                  ? 'Slide toward "Focused" to concentrate on your top areas, or "Balanced" to spread more evenly.'
                  : 'Here\'s where your study time should go, based on what you told us.'}
            </div>

            {editing && !rankMode && (
              <div className="sw-temp-control">
                <label htmlFor="sw-temp">{temperatureLabel(temperature)}</label>
                <input
                  id="sw-temp"
                  type="range"
                  className="sw-temp-slider"
                  min={TEMP_MIN}
                  max={TEMP_MAX}
                  step={0.05}
                  value={temperature}
                  onChange={(e) => setTemperature(Number(e.target.value))}
                  aria-label="Focus: sharper to more balanced"
                />
                <button
                  className="btn btn-ghost sw-temp-reset"
                  onClick={() => setTemperature(TEMP_DEFAULT)}
                  disabled={temperature === TEMP_DEFAULT}
                >
                  Reset
                </button>
                <button className="btn btn-ghost sw-temp-reset" onClick={openRankMode}>
                  Reorder manually
                </button>
              </div>
            )}

            {rankMode ? (
              <div className="sw-ranking">
                {rankOrder.map((s, i) => (
                  <div key={s} className="sw-rank-row">
                    <span className="sw-rank-num">{i + 1}</span>
                    <span className="sw-name">{s}</span>
                    <button className="icon-btn" disabled={i === 0} onClick={() => moveRank(i, -1)} aria-label="Move up">
                      <Icon name="chevronDown" style={{ transform: 'rotate(180deg)' }} />
                    </button>
                    <button className="icon-btn" disabled={i === rankOrder.length - 1} onClick={() => moveRank(i, 1)} aria-label="Move down">
                      <Icon name="chevronDown" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              order.map((s) => (
                <div key={s} className="sw-row">
                  <span className="sw-name" title={s}>{s}</span>
                  <span className="sw-bar-track">
                    <span className="sw-bar-fill" style={{ width: `${display[s] ?? 0}%` }} />
                  </span>
                  <span className="sw-value">{(display[s] ?? 0).toFixed(1)}%</span>
                </div>
              ))
            )}

            <div className="sw-actions">
              <button className="btn btn-ghost" onClick={reset}>Start over</button>
              {rankMode ? (
                <button className="btn btn-accent" onClick={applyRanking}>Apply order</button>
              ) : (
                <button className="btn btn-ghost" onClick={() => setEditing((v) => !v)}>
                  {editing ? 'Done' : 'Edit'}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
