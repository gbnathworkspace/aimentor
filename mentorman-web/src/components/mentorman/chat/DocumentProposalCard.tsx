'use client';

import React, { useMemo } from 'react';
import { Icon } from '../icons';
import { StyleNoteReplacementCard } from './StyleNoteReplacementCard';
import type { StyleNote } from '@/lib/mentorman-api';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Proposal {
  id: string;
  /** ProposableField value ("style_note" or "focus_areas") */
  field: string;
  proposedValue: Record<string, unknown>;
  reason: string;
  sourceFilename: string;
  status: 'pending' | 'accepted' | 'dismissed';
  /** Flagged by backend when user already has 5 style notes (max). */
  requires_replacement?: boolean;
}

export interface FailedFile {
  filename: string;
  reason: string;
}

export interface DocumentProposalCardProps {
  jobId: string;
  proposals: Proposal[];
  failedFiles?: FailedFile[];
  /** When true, display applied changes as read-only informational summary. */
  skipReview?: boolean;
  /** Existing style notes from the user's profile (used for replacement flow). */
  existingStyleNotes?: StyleNote[];
  onAccept: (proposalId: string) => void;
  onDismiss: (proposalId: string) => void;
  onAcceptAll: () => void;
  /** Called when user selects an existing style note to replace with a proposed one. */
  onReplace?: (proposalId: string, replacedNoteIndex: number) => void;
  /** Shows a close button on the resolved/applied summary — dismisses the card back to idle. */
  onClose?: () => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Human-friendly label for a ProposableField key. */
function fieldLabel(field: string): string {
  switch (field) {
    case 'style_note': return 'Style Note';
    case 'focus_areas': return 'Focus Area';
    default: return field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

/** Render proposed value as a concise display string. */
function formatProposedValue(field: string, value: Record<string, unknown>): string {
  if (field === 'style_note') {
    const note = value.note ?? value.value;
    const category = value.category;
    if (category && note) return `[${category}] ${note}`;
    if (note) return String(note);
  }
  if (field === 'focus_areas') {
    return String(value.value ?? value.focus_area ?? JSON.stringify(value));
  }
  // Fallback: show stringified value
  const str = JSON.stringify(value);
  return str.length > 80 ? str.slice(0, 77) + '...' : str;
}

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * DocumentProposalCard — interactive chat card displaying L1 memory proposals
 * extracted from uploaded documents.
 *
 * - Displays each proposal with field name, proposed value, and source filename
 * - Provides individual accept/dismiss controls per proposal
 * - Provides an "Apply All" button for batch acceptance
 * - When all proposals are resolved, replaces interactive controls with read-only summary
 * - When skipReview=true, displays applied changes as informational read-only summary
 *
 * Requirements: 5.2, 5.3, 5.5, 5.6, 6.5, 6.9
 */
export function DocumentProposalCard({
  jobId,
  proposals,
  failedFiles,
  skipReview = false,
  existingStyleNotes,
  onAccept,
  onDismiss,
  onAcceptAll,
  onReplace,
  onClose,
}: DocumentProposalCardProps) {
  // Derived state
  const allResolved = useMemo(
    () => proposals.length > 0 && proposals.every((p) => p.status !== 'pending'),
    [proposals]
  );

  const pendingCount = useMemo(
    () => proposals.filter((p) => p.status === 'pending').length,
    [proposals]
  );

  const acceptedCount = useMemo(
    () => proposals.filter((p) => p.status === 'accepted').length,
    [proposals]
  );

  const dismissedCount = useMemo(
    () => proposals.filter((p) => p.status === 'dismissed').length,
    [proposals]
  );

  // ── Skip Review: read-only informational summary ──
  if (skipReview) {
    return (
      <div className="doc-proposal-card doc-proposal-card--readonly" data-job-id={jobId}>
        <div className="doc-proposal-card-header">
          <Icon name="doc" size={15} />
          <span className="doc-proposal-card-title">Document Analysis Complete</span>
          <span className="upload-msg-badge ok">Applied</span>
          {onClose && (
            <button type="button" className="doc-proposal-card-close" title="Close" aria-label="Close" onClick={onClose}>
              <Icon name="x" size={13} />
            </button>
          )}
        </div>
        <p className="doc-proposal-card-subtitle">
          {proposals.length} {proposals.length === 1 ? 'change' : 'changes'} applied directly to your profile.
        </p>
        <div className="doc-proposal-list">
          {proposals.map((proposal) => (
            <div key={proposal.id} className="doc-proposal-item doc-proposal-item--accepted">
              <div className="doc-proposal-item-header">
                <span className="doc-proposal-field">{fieldLabel(proposal.field)}</span>
                <span className="doc-proposal-source">{proposal.sourceFilename}</span>
              </div>
              <div className="doc-proposal-value">
                {formatProposedValue(proposal.field, proposal.proposedValue)}
              </div>
            </div>
          ))}
        </div>
        {failedFiles && failedFiles.length > 0 && (
          <FailedFilesList failedFiles={failedFiles} />
        )}
      </div>
    );
  }

  // ── All proposals resolved: read-only summary ──
  if (allResolved) {
    return (
      <div className="doc-proposal-card doc-proposal-card--resolved" data-job-id={jobId}>
        <div className="doc-proposal-card-header">
          <Icon name="doc" size={15} />
          <span className="doc-proposal-card-title">Document Proposals Resolved</span>
          <span className="upload-msg-badge ok">Done</span>
          {onClose && (
            <button type="button" className="doc-proposal-card-close" title="Close" aria-label="Close" onClick={onClose}>
              <Icon name="x" size={13} />
            </button>
          )}
        </div>
        <div className="doc-proposal-summary">
          {acceptedCount > 0 && (
            <span className="doc-proposal-summary-item doc-proposal-summary-item--accepted">
              <Icon name="check" size={12} />
              {acceptedCount} accepted
            </span>
          )}
          {dismissedCount > 0 && (
            <span className="doc-proposal-summary-item doc-proposal-summary-item--dismissed">
              <Icon name="x" size={12} />
              {dismissedCount} dismissed
            </span>
          )}
        </div>
        {failedFiles && failedFiles.length > 0 && (
          <FailedFilesList failedFiles={failedFiles} />
        )}
      </div>
    );
  }

  // ── Interactive card with accept/dismiss controls ──
  return (
    <div className="doc-proposal-card" data-job-id={jobId}>
      <div className="doc-proposal-card-header">
        <Icon name="spark" size={15} />
        <span className="doc-proposal-card-title">Proposed Profile Changes</span>
        <span className="upload-msg-badge info">{pendingCount} pending</span>
      </div>
      <p className="doc-proposal-card-subtitle">
        Review the extracted information below. Accept to add to your profile or dismiss to discard.
      </p>

      {/* Apply All button */}
      {pendingCount > 1 && (
        <button
          type="button"
          className="btn btn-accent btn-sm doc-proposal-apply-all"
          onClick={onAcceptAll}
          aria-label="Apply all pending proposals"
        >
          <Icon name="check" size={12} />
          Apply All ({pendingCount})
        </button>
      )}

      {/* Proposal list */}
      <div className="doc-proposal-list">
        {proposals.map((proposal) =>
          proposal.requires_replacement && proposal.field === 'style_note' ? (
            <StyleNoteReplacementCard
              key={proposal.id}
              proposalId={proposal.id}
              proposedNote={{
                category: String(proposal.proposedValue.category ?? ''),
                note: String(proposal.proposedValue.note ?? ''),
                source_quote: proposal.proposedValue.source_quote
                  ? String(proposal.proposedValue.source_quote)
                  : undefined,
              }}
              sourceFilename={proposal.sourceFilename}
              reason={proposal.reason}
              existingNotes={existingStyleNotes}
              onReplace={(id, index) => onReplace?.(id, index)}
              onDismiss={onDismiss}
            />
          ) : (
            <ProposalItem
              key={proposal.id}
              proposal={proposal}
              onAccept={onAccept}
              onDismiss={onDismiss}
            />
          )
        )}
      </div>

      {failedFiles && failedFiles.length > 0 && (
        <FailedFilesList failedFiles={failedFiles} />
      )}
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ProposalItem({
  proposal,
  onAccept,
  onDismiss,
}: {
  proposal: Proposal;
  onAccept: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const isPending = proposal.status === 'pending';
  const isAccepted = proposal.status === 'accepted';
  const isDismissed = proposal.status === 'dismissed';

  const statusClass = isAccepted
    ? 'doc-proposal-item--accepted'
    : isDismissed
    ? 'doc-proposal-item--dismissed'
    : '';

  return (
    <div className={`doc-proposal-item ${statusClass}`}>
      <div className="doc-proposal-item-header">
        <span className="doc-proposal-field">{fieldLabel(proposal.field)}</span>
        <span className="doc-proposal-source">{proposal.sourceFilename}</span>
      </div>
      <div className="doc-proposal-value">
        {formatProposedValue(proposal.field, proposal.proposedValue)}
      </div>
      {proposal.reason && (
        <div className="doc-proposal-reason">{proposal.reason}</div>
      )}
      <div className="doc-proposal-actions">
        {isPending ? (
          <>
            <button
              type="button"
              className="btn btn-sm doc-proposal-btn-accept"
              onClick={() => onAccept(proposal.id)}
              aria-label={`Accept ${fieldLabel(proposal.field)} proposal`}
            >
              <Icon name="check" size={12} />
              Accept
            </button>
            <button
              type="button"
              className="btn btn-sm btn-ghost doc-proposal-btn-dismiss"
              onClick={() => onDismiss(proposal.id)}
              aria-label={`Dismiss ${fieldLabel(proposal.field)} proposal`}
            >
              <Icon name="x" size={12} />
              Dismiss
            </button>
          </>
        ) : (
          <span className={`doc-proposal-status-badge ${isAccepted ? 'ok' : 'muted'}`}>
            {isAccepted ? 'Accepted' : 'Dismissed'}
          </span>
        )}
      </div>
    </div>
  );
}

function FailedFilesList({ failedFiles }: { failedFiles: FailedFile[] }) {
  return (
    <div className="doc-proposal-failed">
      <div className="doc-proposal-failed-title">
        <Icon name="warn" size={12} />
        {failedFiles.length} {failedFiles.length === 1 ? 'file' : 'files'} could not be processed
      </div>
      <ul className="doc-proposal-failed-list">
        {failedFiles.map((f, i) => (
          <li key={i}>
            <span className="doc-proposal-failed-name">{f.filename}</span>
            <span className="doc-proposal-failed-reason">{f.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
