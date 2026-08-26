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
  // 0-100 estimated "caught up" mastery per subtopic — only populated on the
  // goalIntent path (see subtopic_weights.py); null after a manual reorder.
  proficiency: Record<string, number> | null;
}

type Phase = 'loading' | 'result' | 'error';

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

const RADAR_SIZE = 600;
const RADAR_CENTER = RADAR_SIZE / 2;
const RADAR_MAX_R = RADAR_CENTER - 100; // leaves room for perimeter labels
const RADAR_LABEL_R = RADAR_MAX_R + 22;
const RADAR_RINGS = [25, 50, 75, 100];
const RADAR_LABEL_FONT_SIZE = 12;
const RADAR_LABEL_LINE_HEIGHT = 15;
const RADAR_LABEL_MAX_CHARS = 18;
const RADAR_LABEL_MAX_LINES = 3;

// Wraps a subtopic name onto up to RADAR_LABEL_MAX_LINES short lines instead of
// truncating to one line — these are "2-6 word compact noun-phrase" tags (see
// subtopic_weights.py's decompose prompt), so wrapping keeps them legible
// around the perimeter without the aggressive single-line ellipsis this used
// to need. Falls back to a hard-truncated ellipsis only past the line budget.
function wrapLabel(s: string, maxChars = RADAR_LABEL_MAX_CHARS, maxLines = RADAR_LABEL_MAX_LINES): string[] {
  const words = s.split(' ');
  const lines: string[] = [];
  let current = '';
  for (const w of words) {
    const candidate = current ? `${current} ${w}` : w;
    if (candidate.length <= maxChars) {
      current = candidate;
    } else if (current === '') {
      // Single word longer than the line budget — hard-truncate just that word.
      lines.push(`${w.slice(0, Math.max(1, maxChars - 1))}…`);
    } else {
      lines.push(current);
      current = w;
    }
  }
  if (current) lines.push(current);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    let last = kept[maxLines - 1];
    while (last.length > maxChars - 1) last = last.slice(0, -1);
    kept[maxLines - 1] = `${last}…`;
    return kept;
  }
  return lines;
}

// Hand-rolled N-axis radar (no chart lib in this repo — see package.json).
// One polygon of "caught up" proficiency per subtopic, evenly spaced by angle,
// with 25/50/75/100 gridlines. Axis order matches the bar list next to it so
// the two stay easy to cross-reference.
function RadarChart({ subtopics, proficiency }: { subtopics: string[]; proficiency: Record<string, number> }) {
  const n = subtopics.length;
  const angleFor = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pointAt = (i: number, value: number): [number, number] => {
    const r = (Math.max(0, Math.min(100, value)) / 100) * RADAR_MAX_R;
    const a = angleFor(i);
    return [RADAR_CENTER + r * Math.cos(a), RADAR_CENTER + r * Math.sin(a)];
  };

  const dataPoints = subtopics.map((s, i) => pointAt(i, proficiency[s] ?? 0));
  const summary = subtopics.map((s) => `${s}: ${Math.round(proficiency[s] ?? 0)}%`).join(', ');

  return (
    <svg
      viewBox={`0 0 ${RADAR_SIZE} ${RADAR_SIZE}`}
      width={RADAR_SIZE}
      height={RADAR_SIZE}
      role="img"
      aria-label={`How caught up you are on each subtopic: ${summary}`}
      className="sw-radar-svg"
    >
      {RADAR_RINGS.map((ring) => (
        <polygon
          key={ring}
          points={subtopics.map((_, i) => pointAt(i, ring).join(',')).join(' ')}
          fill="none"
          stroke="var(--border)"
          strokeWidth={1}
        />
      ))}
      {subtopics.map((s, i) => {
        const [x, y] = pointAt(i, 100);
        return <line key={s} x1={RADAR_CENTER} y1={RADAR_CENTER} x2={x} y2={y} stroke="var(--border)" strokeWidth={1} />;
      })}
      <polygon
        points={dataPoints.map((p) => p.join(',')).join(' ')}
        fill="var(--accent-weak)"
        stroke="var(--accent)"
        strokeWidth={1.5}
      />
      {dataPoints.map(([x, y], i) => (
        <circle key={subtopics[i]} cx={x} cy={y} r={2.5} fill="var(--accent)" />
      ))}
      {subtopics.map((s, i) => {
        const [x, y] = pointAt(i, (RADAR_LABEL_R / RADAR_MAX_R) * 100);
        const lines = wrapLabel(s);
        const startDy = -((lines.length - 1) / 2) * RADAR_LABEL_LINE_HEIGHT;
        return (
          <text key={s} x={x} y={y} fontSize={RADAR_LABEL_FONT_SIZE} fontWeight={550} fill="var(--fg-dim)" textAnchor="middle">
            <title>{s}</title>
            {lines.map((line, li) => (
              <tspan key={li} x={x} dy={li === 0 ? startDy : RADAR_LABEL_LINE_HEIGHT}>
                {line}
              </tspan>
            ))}
          </text>
        );
      })}
    </svg>
  );
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

// L1 facts (situations) are free text appended over time, so near-restatements pile up
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

// Suggests quick-pick goals from the user's existing L1 profile (facts,
// learning context) instead of making them type evidence from scratch every
// time — "Something else" (rendered separately, not a GoalCard) is the escape
// hatch back to pasting specific work evidence.
//
// Facts are profile-wide, not topic-scoped, so they may only partly
// overlap the topic being weighted — classify_relevance judges the actual
// overlap (see .kiro/specs/topic-scoping), and `l1Scope` here is that
// judgment's cached output: any fact / context label it marked
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
  // be first in the user's raw situations list.
  const candidates = (profile?.learning_context_detail?.situations ?? []).filter((a) => !irrelevant.has(a));
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
  /** Opens the topic's Scoped User Memory modal (chat.tsx's L1MemoryModal).
   *  Omitted → the button isn't shown. */
  onOpenL1Memory?: () => void;
}

export function SubtopicWeightsModal({ open, onClose, topicId, topicTitle, profile, l1Scope, onOpenL1Memory }: SubtopicWeightsModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  const [phase, setPhase] = useState<Phase>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  const goalCards = useMemo(
    () => buildGoalCards(profile, topicTitle || 'this topic', l1Scope),
    [profile, topicTitle, l1Scope]
  );

  const [baseline, setBaseline] = useState<Record<string, number>>({});
  const [proficiency, setProficiency] = useState<Record<string, number> | null>(null);
  const [temperature, setTemperature] = useState(TEMP_DEFAULT);
  const [editing, setEditing] = useState(false);
  // Manual reorder-to-rank, offered inside Edit as an alternative to the
  // temperature control — not a forced step. Evidence too sparse to count
  // reliably just falls back to an equal split instead of blocking the view.
  const [rankMode, setRankMode] = useState(false);
  const [rankOrder, setRankOrder] = useState<string[]>([]);
  const [order, setOrder] = useState<string[]>([]); // fixed at result time — editing must not reshuffle rows

  const display = useMemo(() => applyTemperature(baseline, temperature), [baseline, temperature]);

  // Radar needs >=3 axes to read as a shape rather than a line/triangle
  // degenerate case — below that, the per-row "caught up" badges (rendered
  // regardless of this count) are the only proficiency UI shown.
  const radarSubtopics = useMemo(
    () => (proficiency ? order.filter((s) => proficiency[s] != null) : []),
    [order, proficiency]
  );
  const showRadar = !rankMode && radarSubtopics.length >= 3;

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  }, [onClose]);

  const runQuery = useCallback(async (
    pairwiseComparisons?: [string, string][],
    intent?: string,
  ) => {
    if (!topicId) return;
    setPhase('loading');
    setErrorMsg('');
    try {
      const res = await fetch(`/api/topic/${topicId}/subtopic-weights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: 'job_performance',
          goalIntent: intent,
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
      setProficiency(data.proficiency ?? null);
      setTemperature(TEMP_DEFAULT);
      setEditing(false);
      setRankMode(false);
      setOrder([...data.subtopics].sort((a, b) => (w[b] ?? 0) - (w[a] ?? 0)));
      setPhase('result');
    } catch {
      setErrorMsg('Request failed — try again.');
      setPhase('error');
    }
  }, [topicId]);

  // Runs weight generation straight from scoped L1 memory — goalCards[0] is
  // classify_relevance's top-ranked focus area (or "Just revising" when
  // nothing qualifies) — no confirm-your-goal step in between.
  const runFromScope = useCallback(() => {
    runQuery(undefined, goalCards[0]?.intent);
  }, [runQuery, goalCards]);

  // Cache the result per topic — reopening the same topic's modal shows what
  // was already computed instead of re-hitting the LLM every time. Only a
  // topic switch or an explicit "Start over"/retry re-runs it.
  const fetchedForTopic = useRef<string | null>(null);
  useEffect(() => {
    if (open) dialogRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open && topicId && fetchedForTopic.current !== topicId) {
      fetchedForTopic.current = topicId;
      runFromScope();
    }
  }, [open, topicId, runFromScope]);

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
        className={`sw-dialog${showRadar ? ' sw-dialog--chart' : ''}`}
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
          <div className="sw-head-actions">
            {onOpenL1Memory && (
              <button
                className="icon-btn"
                title="Scoped User Memory for this topic"
                aria-label="Scoped User Memory for this topic"
                onClick={onOpenL1Memory}
              >
                <Icon name="brain" />
              </button>
            )}
            <button className="icon-btn" title="Close" aria-label="Close" onClick={onClose}>
              <Icon name="x" />
            </button>
          </div>
        </div>

        {phase === 'loading' && (
          <div className="sw-status">Figuring out where to focus, from your scoped memory…</div>
        )}

        {phase === 'error' && (
          <div className="sw-status sw-status-error">
            {errorMsg}
            <button className="btn btn-ghost sw-back" onClick={runFromScope}>Retry</button>
          </div>
        )}

        {phase === 'result' && (
          <div className="sw-body">
            <div className="sw-hint">
              {rankMode
                ? 'Drag from most to least important — we\'ll work out the rest from your order.'
                : editing
                  ? 'Slide toward "Focused" to concentrate on your top areas, or "Balanced" to spread more evenly.'
                  : `Here's where your study time should go, based on your scoped focus: ${goalCards[0]?.title ?? topicTitle ?? 'this topic'}.`}
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
              <div className="sw-cols">
                <div className="sw-bars">
                  {proficiency && (
                    <div className="sw-legend">
                      <span className="sw-legend-item"><span className="sw-legend-swatch sw-legend-swatch--bar" />Study time</span>
                      <span className="sw-legend-item"><span className="sw-legend-swatch sw-legend-swatch--radar" />Caught up</span>
                    </div>
                  )}
                  {order.map((s) => (
                    <div key={s} className="sw-row">
                      <span className="sw-name" title={s}>{s}</span>
                      <span className="sw-bar-track">
                        <span className="sw-bar-fill" style={{ width: `${display[s] ?? 0}%` }} />
                      </span>
                      <span className="sw-value">{(display[s] ?? 0).toFixed(1)}%</span>
                      {proficiency && proficiency[s] != null && (
                        <span className="sw-proficiency">{Math.round(proficiency[s])}% caught up</span>
                      )}
                    </div>
                  ))}
                </div>
                {showRadar && (
                  <div className="sw-radar-col">
                    <div className="sw-radar-title">Caught up, by subtopic</div>
                    <RadarChart subtopics={radarSubtopics} proficiency={proficiency!} />
                  </div>
                )}
              </div>
            )}

            <div className="sw-actions">
              <button className="btn btn-ghost" onClick={runFromScope}>Start over</button>
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
