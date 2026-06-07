'use client';

import React from 'react';
import { Icon } from '../icons';

export type UploadStatus =
  | 'uploading'
  | 'pending'
  | 'processing'
  | 'ready'
  | 'done'
  | 'partial'
  | 'failed'
  | 'timeout'
  | 'connection_lost';

export interface UploadMessageProps {
  jobId: string;
  filename: string;
  fileType: 'resume' | 'leetcode';
  status: UploadStatus;
  summary?: string;
  error?: string;
  onRetry?: () => void;
  onRefresh?: () => void;
}

/** Map status to badge label and color variant */
function getStatusBadge(status: UploadStatus): { label: string; variant: 'info' | 'warn' | 'ok' | 'danger' | 'muted' } {
  switch (status) {
    case 'uploading':       return { label: 'Uploading', variant: 'info' };
    case 'pending':         return { label: 'Pending', variant: 'muted' };
    case 'processing':      return { label: 'Processing', variant: 'info' };
    case 'ready':           return { label: 'Ready', variant: 'ok' };
    case 'done':            return { label: 'Ingested', variant: 'ok' };
    case 'partial':         return { label: 'Partial', variant: 'warn' };
    case 'failed':          return { label: 'Failed', variant: 'danger' };
    case 'timeout':         return { label: 'Timeout', variant: 'warn' };
    case 'connection_lost': return { label: 'Connection Lost', variant: 'danger' };
  }
}

/**
 * UploadMessage — rendered in the conversation timeline to represent
 * a file upload event. Shows filename, file type icon, status badge,
 * progress indicator, summary, and error/info messages depending on state.
 *
 * Requirements: 1.5, 1.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8
 */
export function UploadMessage({
  jobId,
  filename,
  fileType,
  status,
  summary,
  error,
  onRetry,
  onRefresh,
}: UploadMessageProps) {
  const badge = getStatusBadge(status);

  return (
    <div className="upload-message" data-job-id={jobId}>
      {/* Header row: icon + filename + badge */}
      <div className="upload-msg-header">
        <span className="upload-msg-icon">
          <Icon name={fileType === 'leetcode' ? 'code' : 'doc'} size={15} />
        </span>
        <span className="upload-msg-filename">{filename}</span>
        <span className={`upload-msg-badge ${badge.variant}`}>
          {badge.label}
        </span>
      </div>

      {/* Indeterminate progress bar while uploading */}
      {status === 'uploading' && (
        <div className="upload-msg-progress" role="progressbar" aria-label="Uploading file">
          <div className="upload-msg-progress-bar" />
        </div>
      )}

      {/* Extraction summary when ready */}
      {status === 'ready' && summary && (
        <div className="upload-msg-summary">
          {summary.length > 80 ? summary.slice(0, 80) : summary}
        </div>
      )}

      {/* Partial explanation */}
      {status === 'partial' && (
        <div className="upload-msg-detail warn">
          Structured data saved, but embedding failed.
        </div>
      )}

      {/* Failed — show error from Job_Record */}
      {status === 'failed' && error && (
        <div className="upload-msg-detail danger">
          {error}
        </div>
      )}

      {/* Timeout informational message */}
      {status === 'timeout' && (
        <div className="upload-msg-detail warn">
          Processing is taking longer than expected. You may continue chatting.
        </div>
      )}

      {/* Connection Lost — show refresh button */}
      {status === 'connection_lost' && (
        <div className="upload-msg-detail danger">
          <span>Unable to reach the server.</span>
          {onRefresh && (
            <button
              type="button"
              className="btn btn-sm btn-ghost upload-msg-refresh-btn"
              onClick={onRefresh}
            >
              Refresh Status
            </button>
          )}
        </div>
      )}

      {/* Retry button for failed uploads */}
      {status === 'failed' && onRetry && (
        <button
          type="button"
          className="btn btn-sm btn-ghost upload-msg-retry-btn"
          onClick={onRetry}
        >
          Retry
        </button>
      )}
    </div>
  );
}
