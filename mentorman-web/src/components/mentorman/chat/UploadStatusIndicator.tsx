'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Job status values returned by the backend.
 * Non-terminal: pending, extracting, synthesizing (keep polling)
 * Terminal: done, failed (stop polling)
 */
export type DocumentJobStatus =
  | 'pending'
  | 'extracting'
  | 'synthesizing'
  | 'done'
  | 'failed';

/** Status response from GET /api/documents/jobs/{jobId}/status */
export interface JobStatusResponse {
  jobId: string;
  status: DocumentJobStatus;
  files: Array<{ filename: string; status: string }>;
  proposals: unknown[] | null;
  failedFiles: Array<{ filename: string; reason: string }>;
  createdAt: string;
}

export interface UploadStatusIndicatorProps {
  /** The upload job ID to poll status for. */
  jobId: string;
  /** Called whenever the job status changes. */
  onStatusChange?: (status: DocumentJobStatus, data: JobStatusResponse) => void;
  /** Called when the job reaches the `done` state. */
  onDone?: (data: JobStatusResponse) => void;
  /** Called when the job reaches the `failed` state. */
  onFailed?: (data: JobStatusResponse) => void;
}

/** Maps non-terminal statuses to user-facing stage labels. */
const STAGE_LABELS: Record<string, string> = {
  pending: 'Uploading files...',
  extracting: 'Reading documents...',
  synthesizing: 'Analyzing content...',
};

/** Terminal statuses that stop polling. */
const TERMINAL_STATUSES: Set<string> = new Set(['done', 'failed']);

/** Polling interval in milliseconds (2 seconds). */
const POLL_INTERVAL_MS = 2000;

/**
 * UploadStatusIndicator — displays processing state for a document upload job
 * in the chat timeline with an animated spinner and stage-appropriate label.
 *
 * Polls `GET /api/documents/jobs/{jobId}/status` every 2 seconds while the job
 * is in a non-terminal state (pending, extracting, synthesizing). Stops polling
 * when the job reaches `done` or `failed`.
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.10
 */
export function UploadStatusIndicator({
  jobId,
  onStatusChange,
  onDone,
  onFailed,
}: UploadStatusIndicatorProps) {
  const [status, setStatus] = useState<DocumentJobStatus>('pending');
  const [label, setLabel] = useState<string>(STAGE_LABELS.pending);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    if (!mountedRef.current) return;

    try {
      const response = await fetch(`/api/documents/jobs/${jobId}/status`);
      if (!response.ok) {
        // Schedule next poll on error (non-terminal)
        if (mountedRef.current) {
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
        return;
      }

      const data: JobStatusResponse = await response.json();
      if (!mountedRef.current) return;

      const newStatus = data.status as DocumentJobStatus;

      setStatus(newStatus);
      setLabel(STAGE_LABELS[newStatus] ?? '');

      onStatusChange?.(newStatus, data);

      if (TERMINAL_STATUSES.has(newStatus)) {
        // Stop polling on terminal state
        stopPolling();
        if (newStatus === 'done') {
          onDone?.(data);
        } else if (newStatus === 'failed') {
          onFailed?.(data);
        }
        return;
      }

      // Schedule next poll for non-terminal states
      timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    } catch {
      // Network error — keep polling
      if (mountedRef.current) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }
  }, [jobId, onStatusChange, onDone, onFailed, stopPolling]);

  useEffect(() => {
    mountedRef.current = true;

    // Start first poll immediately
    poll();

    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Don't render anything once terminal state is reached
  if (TERMINAL_STATUSES.has(status)) {
    return null;
  }

  return (
    <div
      className="upload-status-indicator"
      data-job-id={jobId}
      data-status={status}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <span className="upload-status-spinner" aria-hidden="true" />
      <span className="upload-status-label">{label}</span>
    </div>
  );
}
