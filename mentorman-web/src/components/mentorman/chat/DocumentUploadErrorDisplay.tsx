'use client';

import React, { useState, useCallback } from 'react';
import { Icon } from '../icons';
import type { FailedFile } from './DocumentProposalCard';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DocumentUploadErrorDisplayProps {
  /** The upload job ID. */
  jobId: string;
  /** Terminal status of the job: 'done' (no proposals) or 'failed'. */
  jobStatus: 'done' | 'failed';
  /** List of files that failed extraction. */
  failedFiles?: FailedFile[];
  /** Whether the failure was a network/upload error (not a job processing failure). */
  isNetworkError?: boolean;
  /** Error message for network failures. */
  networkErrorMessage?: string;
  /** Number of consecutive network retry failures so far. */
  consecutiveFailures?: number;
  /** Called when user clicks "Retry" for failed file re-upload. Re-uses selected files. */
  onRetryUpload?: () => void;
  /** Called when user clicks "Retry Analysis" to re-run synthesis. */
  onRetryAnalysis?: () => void;
  /** Shows a close button in the header — dismisses the card back to idle. */
  onClose?: () => void;
}

function CloseButton({ onClose }: { onClose?: () => void }) {
  if (!onClose) return null;
  return (
    <button type="button" className="doc-proposal-card-close" title="Close" aria-label="Close" onClick={onClose}>
      <Icon name="x" size={13} />
    </button>
  );
}

/** Maximum consecutive network failures before disabling retry. */
const MAX_CONSECUTIVE_FAILURES = 3;

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * DocumentUploadErrorDisplay — handles error states and retry functionality
 * for the document upload pipeline.
 *
 * Displays:
 * - "No proposals found" informational message when job completes with no proposals
 * - Per-file failure reasons with "Retry" button when job fails
 * - Network failure error message with "Retry" button (re-uses selected files)
 * - Disables retry after 3 consecutive network failures
 * - "Retry Analysis" button for re-running LLM synthesis on preserved text
 *
 * Requirements: 6.6, 6.7, 6.8, 9.1, 9.2, 9.6
 */
export function DocumentUploadErrorDisplay({
  jobId,
  jobStatus,
  failedFiles = [],
  isNetworkError = false,
  networkErrorMessage,
  consecutiveFailures = 0,
  onRetryUpload,
  onRetryAnalysis,
  onClose,
}: DocumentUploadErrorDisplayProps) {
  const [retryAnalysisLoading, setRetryAnalysisLoading] = useState(false);
  const [retryAnalysisError, setRetryAnalysisError] = useState<string | null>(null);

  const retriesExhausted = consecutiveFailures >= MAX_CONSECUTIVE_FAILURES;

  /**
   * Handles "Retry Analysis" button click.
   * Calls POST /api/documents/jobs/{jobId}/retry-analysis.
   * Requirements: 9.6
   */
  const handleRetryAnalysis = useCallback(async () => {
    setRetryAnalysisLoading(true);
    setRetryAnalysisError(null);

    try {
      const response = await fetch(`/api/documents/jobs/${jobId}/retry-analysis`, {
        method: 'POST',
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({ detail: 'Retry failed' }));
        setRetryAnalysisError(data.detail ?? `Retry failed (HTTP ${response.status})`);
      }
      // On success, the parent should re-poll status to pick up the new synthesis run.
      // The onRetryAnalysis callback can trigger that.
      onRetryAnalysis?.();
    } catch {
      setRetryAnalysisError('Network error — could not reach the server.');
    } finally {
      setRetryAnalysisLoading(false);
    }
  }, [jobId, onRetryAnalysis]);

  // ── Case 1: Network upload failure (Requirements: 9.1, 9.2) ──
  if (isNetworkError) {
    return (
      <div
        className="doc-upload-error-display doc-upload-error-display--network"
        data-job-id={jobId}
        role="alert"
      >
        <div className="doc-upload-error-header">
          <Icon name="warn" size={14} />
          <span className="doc-upload-error-title">Upload Failed</span>
          <CloseButton onClose={onClose} />
        </div>
        <p className="doc-upload-error-message">
          {networkErrorMessage || 'Upload could not be completed due to a network issue.'}
        </p>
        {retriesExhausted ? (
          <p className="doc-upload-error-exhausted">
            Upload is currently unavailable. Please try again later.
          </p>
        ) : (
          <button
            type="button"
            className="btn btn-sm btn-ghost doc-upload-retry-btn"
            onClick={onRetryUpload}
            disabled={retriesExhausted}
            aria-label="Retry upload"
          >
            <Icon name="arrowUp" size={12} />
            Retry
          </button>
        )}
      </div>
    );
  }

  // ── Case 2: Job done with no proposals (Requirement: 6.6) ──
  if (jobStatus === 'done' && failedFiles.length === 0) {
    return (
      <div
        className="doc-upload-error-display doc-upload-error-display--no-proposals"
        data-job-id={jobId}
        role="status"
      >
        <div className="doc-upload-error-header">
          <Icon name="doc" size={14} />
          <span className="doc-upload-error-title">Analysis Complete</span>
          <span className="upload-msg-badge muted">No Changes</span>
          <CloseButton onClose={onClose} />
        </div>
        <p className="doc-upload-error-message">
          No profile-relevant information was found in the uploaded documents. The content
          may not contain details about your learning goals, preferences, or background.
        </p>
      </div>
    );
  }

  // ── Case 3: Job failed — per-file failures (Requirement: 6.7) ──
  // ── Case 4: Job done with proposals AND failed files is handled by
  //    DocumentProposalCard (which includes FailedFilesList). This component
  //    only renders when there are NO proposals (Requirement: 6.8 is covered
  //    by DocumentProposalCard receiving failedFiles prop). ──
  if (jobStatus === 'failed') {
    return (
      <div
        className="doc-upload-error-display doc-upload-error-display--failed"
        data-job-id={jobId}
        role="alert"
      >
        <div className="doc-upload-error-header">
          <Icon name="warn" size={14} />
          <span className="doc-upload-error-title">Processing Failed</span>
          <span className="upload-msg-badge danger">Failed</span>
          <CloseButton onClose={onClose} />
        </div>

        {/* Per-file failure reasons */}
        {failedFiles.length > 0 && (
          <div className="doc-upload-error-files">
            <ul className="doc-proposal-failed-list">
              {failedFiles.map((f, i) => (
                <li key={i}>
                  <span className="doc-proposal-failed-name">{f.filename}</span>
                  <span className="doc-proposal-failed-reason">{f.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action buttons */}
        <div className="doc-upload-error-actions">
          {/* Retry upload for failed files (Requirement: 6.7) */}
          {onRetryUpload && (
            <button
              type="button"
              className="btn btn-sm btn-ghost doc-upload-retry-btn"
              onClick={onRetryUpload}
              aria-label="Retry upload for failed files"
            >
              <Icon name="arrowUp" size={12} />
              Retry
            </button>
          )}

          {/* Retry Analysis button — when extraction succeeded but synthesis failed (Requirement: 9.6) */}
          {onRetryAnalysis && (
            <button
              type="button"
              className="btn btn-sm btn-ghost doc-upload-retry-analysis-btn"
              onClick={handleRetryAnalysis}
              disabled={retryAnalysisLoading}
              aria-label="Retry analysis using preserved text"
            >
              <Icon name="spark" size={12} />
              {retryAnalysisLoading ? 'Retrying...' : 'Retry Analysis'}
            </button>
          )}
        </div>

        {/* Retry analysis error feedback */}
        {retryAnalysisError && (
          <p className="doc-upload-error-inline">{retryAnalysisError}</p>
        )}
      </div>
    );
  }

  // ── Case 5: Job done with failed files but no proposals ──
  // This handles the edge where job is 'done', no proposals were generated,
  // but some files failed. Shows both the "no proposals" message and failures.
  if (jobStatus === 'done' && failedFiles.length > 0) {
    return (
      <div
        className="doc-upload-error-display doc-upload-error-display--partial"
        data-job-id={jobId}
        role="status"
      >
        <div className="doc-upload-error-header">
          <Icon name="doc" size={14} />
          <span className="doc-upload-error-title">Analysis Complete</span>
          <span className="upload-msg-badge warn">Partial</span>
          <CloseButton onClose={onClose} />
        </div>
        <p className="doc-upload-error-message">
          No profile-relevant information was found in the successfully processed documents.
        </p>

        {/* Failed files list */}
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

        {/* Retry button for the failed files */}
        {onRetryUpload && (
          <button
            type="button"
            className="btn btn-sm btn-ghost doc-upload-retry-btn"
            onClick={onRetryUpload}
            aria-label="Retry upload for failed files"
          >
            <Icon name="arrowUp" size={12} />
            Retry Failed Files
          </button>
        )}
      </div>
    );
  }

  // Fallback — should not reach here with valid props
  return null;
}
