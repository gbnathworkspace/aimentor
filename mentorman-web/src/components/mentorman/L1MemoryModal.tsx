import { useState } from 'react';
import { Icon } from './icons';
import type { L1ScopeEntry } from './chat';

export interface L1MemoryModalProps {
  open: boolean;
  topicTitle?: string;
  entries: L1ScopeEntry[];
  /** Reclassify one entry — drag-drop between Relevant/Not relevant calls
   *  this the same way UncertainRelevanceModal's onAnswer does. */
  onResolve: (situation: string, relevant: boolean) => void;
  onClose: () => void;
}

const VERDICT_ORDER = ['relevant', 'uncertain', 'irrelevant'] as const;
type Verdict = (typeof VERDICT_ORDER)[number];
const VERDICT_LABEL: Record<Verdict, string> = {
  relevant: 'Relevant',
  uncertain: 'Uncertain',
  irrelevant: 'Not relevant',
};
// Only these two are droppable — there's no "set back to uncertain" mutation,
// dropping onto one of them is how an "uncertain" entry gets resolved too.
const DROP_TARGETS: Partial<Record<Verdict, boolean>> = { relevant: true, irrelevant: true };

const DRAG_MIME = 'application/x-l1-situation';

/**
 * View of a topic's scoped L1 memory — every situation/context/focus_area
 * classify_relevance has judged, grouped by verdict. Opened from the
 * "target" icon in the topic header; distinct from the goal-picker in
 * SubtopicWeightsModal, which only surfaces a couple of these as pickable
 * cards. This shows the full l1_scope list classify_relevance produced.
 *
 * Drag a row onto "Relevant" or "Not relevant" to override the classifier's
 * call — same resolve endpoint UncertainRelevanceModal uses
 * (POST /topic/{id}/l1-scope/resolve), so a manual move survives a later
 * profile-triggered recompute (TopicService._merge_l1_scope). "Not relevant"
 * starts collapsed — it's the group least likely to need attention.
 */
export function L1MemoryModal({ open, topicTitle, entries, onResolve, onClose }: L1MemoryModalProps) {
  const [collapsed, setCollapsed] = useState<Partial<Record<Verdict, boolean>>>({ irrelevant: true });
  const [dragOver, setDragOver] = useState<Verdict | null>(null);

  if (!open) return null;

  const groups: Record<Verdict, L1ScopeEntry[]> = { relevant: [], uncertain: [], irrelevant: [] };
  for (const e of entries) (groups[e.verdict as Verdict] ?? groups.irrelevant).push(e);

  const toggle = (v: Verdict) => setCollapsed((prev) => ({ ...prev, [v]: !prev[v] }));

  const handleDrop = (target: Verdict) => (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(null);
    const situation = e.dataTransfer.getData(DRAG_MIME);
    if (situation) onResolve(situation, target === 'relevant');
  };

  return (
    <div className="sw-overlay" onClick={onClose}>
      <div
        className="skip-dialog l1-memory-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="l1mem-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sw-head">
          <div>
            <h2 id="l1mem-title" className="sw-title">Scoped User Memory</h2>
            <div className="sw-sub">{topicTitle ? `for ${topicTitle}` : ''}</div>
          </div>
          <button className="icon-btn" title="Close" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        {entries.length === 0 ? (
          <p className="sw-goal-note">Not computed yet for this topic — reopen it in a moment.</p>
        ) : (
          <div className="l1-memory-groups">
            {VERDICT_ORDER.filter((v) => groups[v].length > 0).map((v) => {
              const isOpen = !collapsed[v];
              const droppable = !!DROP_TARGETS[v];
              return (
                <div
                  key={v}
                  className={`l1-memory-group${droppable && dragOver === v ? ' l1-memory-group--dragover' : ''}`}
                  onDragOver={droppable ? (e) => { e.preventDefault(); setDragOver(v); } : undefined}
                  onDragLeave={droppable ? () => setDragOver((cur) => (cur === v ? null : cur)) : undefined}
                  onDrop={droppable ? handleDrop(v) : undefined}
                >
                  <button
                    type="button"
                    className={`l1-memory-group-title l1-memory-group-title--${v}`}
                    onClick={() => toggle(v)}
                    aria-expanded={isOpen}
                  >
                    <Icon name="chevronDown" size={11} style={{ transform: isOpen ? undefined : 'rotate(-90deg)' }} />
                    {VERDICT_LABEL[v]} <span className="l1-memory-group-count">{groups[v].length}</span>
                  </button>
                  {isOpen && groups[v].map((e) => (
                    <div
                      key={e.situation}
                      className="l1-memory-row"
                      draggable
                      onDragStart={(ev) => ev.dataTransfer.setData(DRAG_MIME, e.situation)}
                    >
                      <div className="l1-memory-row-text">{e.situation}</div>
                      {e.reason && <div className="l1-memory-row-reason">{e.reason}</div>}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
