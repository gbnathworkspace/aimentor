'use client';

/**
 * useFileUpload — custom hook encapsulating the chat file upload submission
 * and polling logic.
 *
 * Responsibilities:
 * 1. Upload file + optional message to POST /api/session/{sessionId}/upload
 * 2. On 202, begin polling GET /api/session/{sessionId}/upload/{jobId}/status
 *    at 2-second intervals
 * 3. Stop polling on terminal state (done, partial, failed) or 5-minute timeout
 *    (150 polls)
 * 4. Retry failed poll requests up to 3 consecutive times at 4-second intervals
 *    before showing "Connection Lost"
 * 5. Insert system message when status reaches "ready" (extractionReady: true)
 *
 * Requirements: 1.4, 1.5, 1.12, 6.6, 6.7, 6.8, 6.9
 */

import { useState, useRef, useCallback, useEffect } from 'react';

export type UploadStatus =
  | 'idle'
  | 'uploading'
  | 'pending'
  | 'processing'
  | 'ready'
  | 'done'
  | 'partial'
  | 'failed'
  | 'timeout'
  | 'connection_lost';

export interface UploadState {
  /** Current upload/processing status */
  status: UploadStatus;
  /** Job ID returned by the upload endpoint */
  jobId: string | null;
  /** Filename of the uploaded file */
  filename: string | null;
  /** File type (resume or leetcode) */
  fileType: 'resume' | 'leetcode' | null;
  /** Extraction summary (max 80 chars) when status reaches "ready" */
  summary: string | null;
  /** Error message from the server or network failure */
  error: string | null;
  /** Whether the upload is currently in progress (uploading or polling) */
  isActive: boolean;
  /** Whether a system message has been emitted for the "ready" state */
  readyMessageEmitted: boolean;
  /** Number of upload retry attempts made so far */
  retryCount: number;
  /** Whether max retries (3) have been exhausted */
  retriesExhausted: boolean;
}

export interface UseFileUploadOptions {
  sessionId: string;
  /** Called when the status reaches "ready" — used to insert a system message */
  onReady?: (info: { jobId: string; filename: string; summary: string }) => void;
  /** Called when upload status changes */
  onStatusChange?: (status: UploadStatus) => void;
}

export interface UseFileUploadReturn {
  /** Current upload state */
  state: UploadState;
  /** Submit a file upload with optional accompanying message */
  submit: (file: File, message?: string) => Promise<void>;
  /** Retry the upload with the previously selected file */
  retry: () => Promise<void>;
  /** Manually refresh the job status (for "Connection Lost" recovery) */
  refreshStatus: () => void;
  /** Reset the hook to idle state */
  reset: () => void;
}

/** Polling interval in milliseconds (2 seconds) */
const POLL_INTERVAL_MS = 2000;

/** Maximum number of polls before timeout (60 seconds / 2 seconds = 30) */
const MAX_POLL_COUNT = 30;

/** Retry interval for failed poll requests (4 seconds) */
const POLL_RETRY_INTERVAL_MS = 4000;

/** Maximum consecutive poll failures before showing "Connection Lost" */
const MAX_POLL_RETRIES = 3;

/** Maximum upload retries */
const MAX_UPLOAD_RETRIES = 3;

/** Terminal statuses that stop polling */
const TERMINAL_STATUSES = new Set(['done', 'partial', 'failed']);

const INITIAL_STATE: UploadState = {
  status: 'idle',
  jobId: null,
  filename: null,
  fileType: null,
  summary: null,
  error: null,
  isActive: false,
  readyMessageEmitted: false,
  retryCount: 0,
  retriesExhausted: false,
};

export function useFileUpload({
  sessionId,
  onReady,
  onStatusChange,
}: UseFileUploadOptions): UseFileUploadReturn {
  const [state, setState] = useState<UploadState>(INITIAL_STATE);

  // Refs to manage polling lifecycle without stale closures
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef(0);
  const consecutiveFailuresRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastFileRef = useRef<File | null>(null);
  const lastMessageRef = useRef<string | undefined>(undefined);
  const uploadRetryCountRef = useRef(0);
  const readyEmittedRef = useRef(false);
  const filenameRef = useRef<string | null>(null);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      stopPolling();
      abortControllerRef.current?.abort();
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const updateState = useCallback(
    (partial: Partial<UploadState>) => {
      setState((prev) => {
        const next = { ...prev, ...partial };
        if (partial.status && partial.status !== prev.status) {
          onStatusChange?.(partial.status);
        }
        return next;
      });
    },
    [onStatusChange]
  );

  /**
   * Polls the job status endpoint. Handles retries on network failure
   * and stops on terminal states or timeout.
   */
  const pollStatus = useCallback(
    async (jobId: string) => {
      // Check if we've exceeded the max poll count (timeout)
      if (pollCountRef.current >= MAX_POLL_COUNT) {
        stopPolling();
        updateState({
          status: 'timeout',
          isActive: false,
          error: 'Processing is taking longer than expected. You may continue chatting.',
        });
        return;
      }

      pollCountRef.current += 1;

      try {
        const response = await fetch(
          `/api/session/${sessionId}/upload/${jobId}/status`,
          { signal: abortControllerRef.current?.signal }
        );

        if (!response.ok) {
          throw new Error(`Status request failed: ${response.status}`);
        }

        const data = await response.json();
        consecutiveFailuresRef.current = 0; // Reset on success

        // Map server status to our UploadStatus
        const serverStatus: string = data.status;
        let newStatus: UploadStatus;

        if (data.extractionReady && !readyEmittedRef.current) {
          // Extraction is ready — emit system message and show "ready" status
          newStatus = 'ready';
          readyEmittedRef.current = true;

          const summary = data.summary ?? 'File content is now available';
          updateState({
            status: 'ready',
            summary,
            readyMessageEmitted: true,
          });

          onReady?.({
            jobId,
            filename: filenameRef.current ?? 'file',
            summary,
          });
        } else if (TERMINAL_STATUSES.has(serverStatus)) {
          newStatus = serverStatus as UploadStatus;
          stopPolling();
          updateState({
            status: newStatus,
            isActive: false,
            error: data.error ?? null,
            summary: data.summary ?? null,
          });
          return;
        } else if (serverStatus === 'processing') {
          newStatus = 'processing';
          updateState({ status: 'processing' });
        } else {
          newStatus = 'pending';
          updateState({ status: 'pending' });
        }

        // If terminal, stop polling
        if (TERMINAL_STATUSES.has(serverStatus)) {
          stopPolling();
          updateState({ isActive: false });
          return;
        }

        // Schedule next poll
        pollingRef.current = setTimeout(() => pollStatus(jobId), POLL_INTERVAL_MS);
      } catch (err: unknown) {
        // Ignore abort errors (component unmount or intentional cancellation)
        if (err instanceof Error && err.name === 'AbortError') return;

        consecutiveFailuresRef.current += 1;

        if (consecutiveFailuresRef.current >= MAX_POLL_RETRIES) {
          // Exhausted retries — show "Connection Lost"
          stopPolling();
          updateState({
            status: 'connection_lost',
            isActive: false,
            error: 'Connection lost. Click "Refresh Status" to try again.',
          });
          return;
        }

        // Retry at 4-second intervals
        pollingRef.current = setTimeout(
          () => pollStatus(jobId),
          POLL_RETRY_INTERVAL_MS
        );
      }
    },
    [sessionId, stopPolling, updateState, onReady]
  );

  /**
   * Starts polling for a given jobId.
   */
  const startPolling = useCallback(
    (jobId: string) => {
      pollCountRef.current = 0;
      consecutiveFailuresRef.current = 0;
      readyEmittedRef.current = false;
      abortControllerRef.current = new AbortController();

      // Begin first poll after POLL_INTERVAL_MS
      pollingRef.current = setTimeout(() => pollStatus(jobId), POLL_INTERVAL_MS);
    },
    [pollStatus]
  );

  /**
   * Submits a file upload to the session upload endpoint.
   */
  const submit = useCallback(
    async (file: File, message?: string) => {
      // Store for potential retry
      lastFileRef.current = file;
      lastMessageRef.current = message;
      uploadRetryCountRef.current = 0;

      const fileType: 'resume' | 'leetcode' =
        file.name.toLowerCase().endsWith('.csv') ? 'leetcode' : 'resume';

      filenameRef.current = file.name;

      updateState({
        status: 'uploading',
        jobId: null,
        filename: file.name,
        fileType,
        summary: null,
        error: null,
        isActive: true,
        readyMessageEmitted: false,
      });

      try {
        const formData = new FormData();
        formData.append('file', file);
        if (message) {
          formData.append('accompanyingMessage', message);
        }

        const response = await fetch(`/api/session/${sessionId}/upload`, {
          method: 'POST',
          body: formData,
        });

        if (response.status === 202) {
          const data = await response.json();
          const jobId = data.jobId;

          updateState({
            status: 'pending',
            jobId,
          });

          // Begin polling
          startPolling(jobId);
        } else {
          // Server returned an error
          const data = await response.json().catch(() => ({ error: 'Upload failed' }));
          updateState({
            status: 'failed',
            isActive: false,
            error: data.error ?? `Upload failed (${response.status})`,
          });
        }
      } catch (err: unknown) {
        // Network failure
        updateState({
          status: 'failed',
          isActive: false,
          error: 'Upload could not be completed due to a network issue.',
        });
      }
    },
    [sessionId, startPolling, updateState]
  );

  /**
   * Retries the upload using the previously selected file.
   * Allowed up to MAX_UPLOAD_RETRIES (3) times.
   */
  const retry = useCallback(async () => {
    if (!lastFileRef.current) return;

    uploadRetryCountRef.current += 1;
    if (uploadRetryCountRef.current > MAX_UPLOAD_RETRIES) {
      updateState({
        status: 'failed',
        isActive: false,
        error: 'Upload could not be completed. Please try again.',
        retryCount: uploadRetryCountRef.current,
        retriesExhausted: true,
      });
      return;
    }

    updateState({
      retryCount: uploadRetryCountRef.current,
      retriesExhausted: false,
    });

    await submit(lastFileRef.current, lastMessageRef.current);
  }, [submit, updateState]);

  /**
   * Manually refreshes the job status — used after "Connection Lost".
   * Resets the failure counter and resumes polling.
   */
  const refreshStatus = useCallback(() => {
    if (!state.jobId) return;

    consecutiveFailuresRef.current = 0;
    updateState({
      status: 'pending',
      isActive: true,
      error: null,
    });

    // Resume polling
    abortControllerRef.current = new AbortController();
    pollingRef.current = setTimeout(() => pollStatus(state.jobId!), 0);
  }, [state.jobId, pollStatus, updateState]);

  /**
   * Resets the hook to idle state. Cancels any active polling.
   */
  const reset = useCallback(() => {
    stopPolling();
    abortControllerRef.current?.abort();
    pollCountRef.current = 0;
    consecutiveFailuresRef.current = 0;
    uploadRetryCountRef.current = 0;
    lastFileRef.current = null;
    lastMessageRef.current = undefined;
    readyEmittedRef.current = false;
    filenameRef.current = null;
    setState(INITIAL_STATE);
  }, [stopPolling]);

  return {
    state,
    submit,
    retry,
    refreshStatus,
    reset,
  };
}
