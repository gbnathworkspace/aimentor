'use client';

import React, { useEffect, useState } from 'react';
import { Icon } from '../icons';
import type { StyleNote } from '@/lib/mentorman-api';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface StyleNoteReplacementCardProps {
  /** The proposal ID from the document upload job. */
  proposalId: string;
  /** The proposed style note value. */
  proposedNote: {
    category: string;
    note: string;
    source_quote?: string;
  };
  /** Source document filename for traceability. */
  sourceFilename: string;
  /** Reason for the proposal. */
  reason?: string;
  /** Existing style notes from the user's profile (if provided externally). */
  existingNotes?: StyleNote[];
  /** Called when user selects an existing note to replace with the proposed one. */
  onReplace: (proposalId: string, replacedNoteIndex: number) => void;
  /** Called when user dismisses the proposed note (leaves existing unchanged). */
  onDismiss: (proposalId: string) => void;
}

type CardState = 'selecting' | 'replaced' | 'dismissed';

/**
 * StyleNoteReplacementCard — displayed when a style_note proposal arrives
 * and the user already has the maximum of 5 style notes.
 *
 * Shows the proposed note alongside all 5 existing notes, informs the user
 * that the maximum has been reached, and allows them to:
 * - Dismiss the proposal (leave existing notes unchanged)
 * - Select an existing note to replace with the proposed one
 *
 * Requirements: 7.3, 7.4
 */
export function StyleNoteReplacementCard({
  proposalId,
  proposedNote,
  sourceFilename,
  reason,
  existingNotes: externalNotes,
  onReplace,
  onDismiss,
}: StyleNoteReplacementCardProps) {
  const [existingNotes, setExistingNotes] = useState<StyleNote[]>(externalNotes ?? []);
  const [loading, setLoading] = useState(!externalNotes);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [cardState, setCardState] = useState<CardState>('selecting');

  // Fetch existing notes from profile if not provided via props
  useEffect(() => {
    if (externalNotes) {
      setExistingNotes(externalNotes);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetch('/api/profile')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data?.style_notes) {
          setExistingNotes(data.style_notes);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [externalNotes]);

  const handleDismiss = () => {
    setCardState('dismissed');
    onDismiss(proposalId);
  };

  const handleReplace = () => {
    if (selectedIndex === null) return;
    setCardState('replaced');
    onReplace(proposalId, selectedIndex);
  };

  // ── Resolved state: show outcome ──
  if (cardState === 'dismissed') {
    return (
      <div className="style-note-replacement-card style-note-replacement-card--resolved" data-proposal-id={proposalId}>
        <div className="style-note-replacement-header">
          <Icon name="doc" size={15} />
          <span className="style-note-replacement-title">Style Note Proposal</span>
          <span className="doc-proposal-status-badge muted">Dismissed</span>
        </div>
        <p className="style-note-replacement-subtitle">
          Proposed note was dismissed. Your existing style notes remain unchanged.
        </p>
      </div>
    );
  }

  if (cardState === 'replaced') {
    return (
      <div className="style-note-replacement-card style-note-replacement-card--resolved" data-proposal-id={proposalId}>
        <div className="style-note-replacement-header">
          <Icon name="check" size={15} />
          <span className="style-note-replacement-title">Style Note Replaced</span>
          <span className="doc-proposal-status-badge ok">Replaced</span>
        </div>
        <p className="style-note-replacement-subtitle">
          Replaced an existing style note with: <strong>[{proposedNote.category}] {proposedNote.note}</strong>
        </p>
      </div>
    );
  }

  // ── Loading state ──
  if (loading) {
    return (
      <div className="style-note-replacement-card" data-proposal-id={proposalId}>
        <div className="style-note-replacement-header">
          <span className="upload-status-spinner" aria-hidden="true" />
          <span className="style-note-replacement-title">Loading style notes...</span>
        </div>
      </div>
    );
  }

  // ── Interactive selection state ──
  return (
    <div className="style-note-replacement-card" data-proposal-id={proposalId}>
      <div className="style-note-replacement-header">
        <Icon name="spark" size={15} />
        <span className="style-note-replacement-title">Style Note Limit Reached</span>
        <span className="upload-msg-badge warn">Max 5</span>
      </div>

      <p className="style-note-replacement-subtitle">
        You already have the maximum of 5 style notes. To add this new note, select an existing one to replace, or dismiss the proposal.
      </p>

      {/* Proposed note */}
      <div className="style-note-replacement-proposed">
        <div className="style-note-replacement-proposed-label">Proposed Note</div>
        <div className="style-note-replacement-proposed-content">
          <span className="style-note-category-badge">{proposedNote.category}</span>
          <span className="style-note-text">{proposedNote.note}</span>
        </div>
        {reason && (
          <div className="style-note-replacement-reason">{reason}</div>
        )}
        <div className="style-note-replacement-source">
          From: {sourceFilename}
        </div>
      </div>

      {/* Existing notes list */}
      <div className="style-note-replacement-existing">
        <div className="style-note-replacement-existing-label">
          Your Existing Style Notes (select one to replace)
        </div>
        <div className="style-note-replacement-list" role="radiogroup" aria-label="Select a style note to replace">
          {existingNotes.map((note, index) => (
            <button
              key={index}
              type="button"
              className={`style-note-replacement-item ${selectedIndex === index ? 'style-note-replacement-item--selected' : ''}`}
              onClick={() => setSelectedIndex(index)}
              role="radio"
              aria-checked={selectedIndex === index}
              aria-label={`Replace note: [${note.category}] ${note.note}`}
            >
              <span className="style-note-replacement-radio" aria-hidden="true">
                {selectedIndex === index ? '●' : '○'}
              </span>
              <span className="style-note-category-badge">{note.category}</span>
              <span className="style-note-text">{note.note}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="style-note-replacement-actions">
        <button
          type="button"
          className="btn btn-sm doc-proposal-btn-accept"
          onClick={handleReplace}
          disabled={selectedIndex === null}
          aria-label="Replace selected style note with proposed note"
        >
          <Icon name="check" size={12} />
          Replace Selected
        </button>
        <button
          type="button"
          className="btn btn-sm btn-ghost doc-proposal-btn-dismiss"
          onClick={handleDismiss}
          aria-label="Dismiss proposed style note"
        >
          <Icon name="x" size={12} />
          Dismiss
        </button>
      </div>
    </div>
  );
}
