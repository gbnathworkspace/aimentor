import { useEffect, useRef, useState } from 'react';
import { Icon } from './icons';

export interface UncertainL1ScopeItem {
  situation: string;
  reason: string;
}

export interface UncertainRelevanceModalProps {
  open: boolean;
  topicTitle?: string;
  items: UncertainL1ScopeItem[];
  /** Called for Relevant/Not relevant — not for Skip (nothing to persist). */
  onAnswer: (situation: string, relevant: boolean) => void;
  onClose: () => void;
}

/**
 * Steps through l1_scope entries the classifier judged "uncertain" — see
 * .kiro/specs/topic-scoping. One item per screen, dismissible any time;
 * a skipped or dismissed item stays "uncertain" and is asked again next
 * time the topic is opened with it still unresolved.
 */
export function UncertainRelevanceModal({ open, topicTitle, items, onAnswer, onClose }: UncertainRelevanceModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (open) { setIndex(0); dialogRef.current?.focus(); }
  }, [open]);

  if (!open || items.length === 0) return null;
  const item = items[index];
  if (!item) return null;

  const advance = () => {
    if (index + 1 < items.length) setIndex(index + 1);
    else onClose();
  };

  const answer = (relevant: boolean) => {
    onAnswer(item.situation, relevant);
    advance();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  return (
    <div className="sw-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className="sw-dialog urm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="urm-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="sw-head">
          <div>
            <h2 id="urm-title" className="sw-title">Is this relevant?</h2>
            <div className="sw-sub">
              {topicTitle ? `for ${topicTitle}` : ''}{items.length > 1 ? ` · ${index + 1} of ${items.length}` : ''}
            </div>
          </div>
          <button className="icon-btn" title="Close" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        <p className="urm-situation">&ldquo;{item.situation}&rdquo;</p>
        {item.reason && <p className="urm-reason">{item.reason}</p>}

        <div className="urm-actions">
          <button className="btn btn-accent" onClick={() => answer(true)}>Relevant</button>
          <button className="btn btn-ghost" onClick={() => answer(false)}>Not relevant</button>
          <button className="btn btn-ghost" onClick={advance}>Skip</button>
        </div>
      </div>
    </div>
  );
}
