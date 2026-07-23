import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from './icons';

type Goal = 'interview_prep' | 'job_performance';

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

type Phase = 'setup' | 'loading' | 'ranking' | 'result' | 'error';

// Mirrors apply_nudges() in unified-backend/app/services/subtopic_weights.py —
// duplicated here (not called over the network) so dragging a nudge input
// recomputes instantly instead of round-tripping per keystroke.
const NUDGE_CAP = 15;
const FLAG_THRESHOLD = NUDGE_CAP * 0.7;

function applyNudges(baseline: Record<string, number>, nudges: Record<string, number>) {
  const nudged: Record<string, number> = {};
  for (const k of Object.keys(baseline)) {
    const clamped = Math.max(-NUDGE_CAP, Math.min(NUDGE_CAP, nudges[k] ?? 0));
    nudged[k] = baseline[k] + clamped;
  }
  const total = Object.values(nudged).reduce((a, b) => a + b, 0);
  const final: Record<string, number> = {};
  for (const k of Object.keys(nudged)) {
    final[k] = total === 0 ? 100 / Object.keys(nudged).length : (nudged[k] / total) * 100;
  }
  const flagged = new Set(
    Object.keys(baseline).filter((k) => Math.abs(final[k] - baseline[k]) > FLAG_THRESHOLD)
  );
  return { final, flagged };
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

export interface SubtopicWeightsModalProps {
  open: boolean;
  onClose: () => void;
  topicId?: string | null;
  topicTitle?: string;
}

export function SubtopicWeightsModal({ open, onClose, topicId, topicTitle }: SubtopicWeightsModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  const [phase, setPhase] = useState<Phase>('setup');
  const [goal, setGoal] = useState<Goal>('interview_prep');
  const [targetContext, setTargetContext] = useState('');
  const [workEvidence, setWorkEvidence] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const [baseline, setBaseline] = useState<Record<string, number>>({});
  const [nudges, setNudges] = useState<Record<string, number>>({});
  const [display, setDisplay] = useState<Record<string, number>>({});
  const [flagged, setFlagged] = useState<Set<string>>(new Set());
  const [rankOrder, setRankOrder] = useState<string[]>([]);
  const [order, setOrder] = useState<string[]>([]); // fixed at result time — dragging a slider must not reshuffle rows

  const reset = useCallback(() => {
    setPhase('setup');
    setErrorMsg('');
    setNudges({});
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  }, [onClose]);

  useEffect(() => {
    if (open) dialogRef.current?.focus();
    else reset();
  }, [open, reset]);

  const runQuery = useCallback(async (pairwiseComparisons?: [string, string][]) => {
    if (!topicId) return;
    setPhase('loading');
    setErrorMsg('');
    try {
      const res = await fetch(`/api/topic/${topicId}/subtopic-weights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          targetContext: targetContext.trim() || undefined,
          workEvidence: goal === 'job_performance' ? workEvidence.trim() || undefined : undefined,
          pairwiseComparisons,
        }),
      });
      const data: WeightsResponse & { detail?: string } = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || 'Could not derive weights.');
        setPhase('error');
        return;
      }
      if (data.needsPairwise) {
        setRankOrder(data.subtopics);
        setPhase('ranking');
        return;
      }
      const w = data.weights || {};
      setBaseline(w);
      setDisplay(w);
      setFlagged(new Set());
      setOrder([...data.subtopics].sort((a, b) => (w[b] ?? 0) - (w[a] ?? 0)));
      setPhase('result');
    } catch {
      setErrorMsg('Request failed — try again.');
      setPhase('error');
    }
  }, [topicId, goal, targetContext, workEvidence]);

  const submitRanking = useCallback(() => {
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

  const handleNudge = (subtopic: string, value: number) => {
    const nextNudges = { ...nudges, [subtopic]: value };
    const { final, flagged: nextFlagged } = applyNudges(baseline, nextNudges);
    const newlyFlagged = [...nextFlagged].filter((s) => !flagged.has(s));
    setNudges(nextNudges);
    setDisplay(final);
    setFlagged(nextFlagged);

    // Best-effort, fire-and-forget — a flagged disagreement is a signal worth
    // keeping (spec step 6), but losing one to a network hiccup shouldn't
    // interrupt dragging a slider.
    if (newlyFlagged.length && topicId) {
      fetch(`/api/topic/${topicId}/subtopic-weights/nudge-log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          flags: newlyFlagged.map((s) => ({
            subtopic: s, baseline: baseline[s], final: final[s], delta: final[s] - baseline[s],
          })),
        }),
      }).catch(() => {});
    }
  };

  const clearNudges = () => {
    setNudges({});
    setDisplay(baseline);
    setFlagged(new Set());
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
            <h2 id="sw-title" className="sw-title">Subtopic weights</h2>
            <div className="sw-sub">{topicTitle || 'topic'} · DeriveSubtopicWeights</div>
          </div>
          <button className="icon-btn" title="Close" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        {phase === 'setup' && (
          <div className="sw-setup">
            <div className="sw-goal-toggle" role="radiogroup" aria-label="Goal">
              <button
                className={`sw-goal-opt ${goal === 'interview_prep' ? 'on' : ''}`}
                role="radio" aria-checked={goal === 'interview_prep'}
                onClick={() => setGoal('interview_prep')}
              >
                Interview prep
              </button>
              <button
                className={`sw-goal-opt ${goal === 'job_performance' ? 'on' : ''}`}
                role="radio" aria-checked={goal === 'job_performance'}
                onClick={() => setGoal('job_performance')}
              >
                On-the-job
              </button>
            </div>

            <label className="sw-label" htmlFor="sw-context">
              Target context <span className="sw-optional">(optional)</span>
            </label>
            <input
              id="sw-context"
              className="sw-input"
              placeholder={goal === 'interview_prep' ? 'e.g. mid-level backend role' : "e.g. your team's codebase"}
              value={targetContext}
              onChange={(e) => setTargetContext(e.target.value)}
              maxLength={200}
            />

            {goal === 'job_performance' && (
              <>
                <label className="sw-label" htmlFor="sw-evidence">
                  Recent work evidence <span className="sw-required">(required)</span>
                </label>
                <textarea
                  id="sw-evidence"
                  className="sw-textarea"
                  placeholder="Paste recent commit messages, ticket titles, or PR review comments…"
                  value={workEvidence}
                  onChange={(e) => setWorkEvidence(e.target.value)}
                  rows={5}
                  maxLength={20000}
                />
              </>
            )}

            <button
              className="btn btn-accent sw-generate"
              disabled={!topicId || (goal === 'job_performance' && !workEvidence.trim())}
              onClick={() => runQuery()}
            >
              Generate weights
            </button>
          </div>
        )}

        {phase === 'loading' && (
          <div className="sw-status">Deriving weights from evidence…</div>
        )}

        {phase === 'error' && (
          <div className="sw-status sw-status-error">
            {errorMsg}
            <button className="btn btn-ghost sw-back" onClick={reset}>Back</button>
          </div>
        )}

        {phase === 'ranking' && (
          <div className="sw-ranking">
            <div className="sw-status">
              Evidence was too sparse to count reliably — rank these subtopics from
              most to least important (AHP-lite fallback).
            </div>
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
            <button className="btn btn-accent sw-generate" onClick={submitRanking}>
              Submit ranking
            </button>
          </div>
        )}

        {phase === 'result' && (
          <div className="sw-body">
            <div className="sw-hint">Drag a slider to override a weight (±{NUDGE_CAP} pts) — the rest rebalance automatically.</div>
            {order.map((s) => {
              const nudge = nudges[s] ?? 0;
              return (
                <div key={s} className="sw-row">
                  <span className="sw-name" title={s}>
                    {s}
                    {flagged.has(s) && <span className="sw-flag" title="Nudged near the cap relative to the computed weight">⚑</span>}
                  </span>
                  <span className="sw-bar-track">
                    <span className="sw-bar-fill" style={{ width: `${display[s] ?? 0}%` }} />
                  </span>
                  <span className="sw-value">{(display[s] ?? 0).toFixed(1)}%</span>
                  <input
                    type="range"
                    className="sw-nudge-slider"
                    min={-NUDGE_CAP}
                    max={NUDGE_CAP}
                    step={1}
                    value={nudge}
                    onChange={(e) => handleNudge(s, Number(e.target.value))}
                    aria-label={`Nudge ${s}`}
                  />
                  <span className="sw-nudge-value">{nudge > 0 ? `+${nudge}` : nudge}</span>
                </div>
              );
            })}
            <div className="sw-actions">
              <button className="btn btn-ghost" onClick={reset}>New query</button>
              <button className="btn btn-ghost" onClick={clearNudges} disabled={Object.keys(nudges).every((k) => !nudges[k])}>
                Reset nudges
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
