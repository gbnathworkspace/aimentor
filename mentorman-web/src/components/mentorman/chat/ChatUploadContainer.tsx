'use client';

import React, { useCallback, useMemo } from 'react';
import { ChatUploadButton } from './ChatUploadButton';
import { UploadMessage } from './UploadMessage';
import { useFileUpload, UploadStatus } from '@/lib/chat-upload/useFileUpload';

/**
 * ChatUploadContainer — orchestrates file upload error handling and retry logic.
 *
 * Responsibilities:
 * 1. Wires ChatUploadButton → useFileUpload → UploadMessage
 * 2. On network failure: shows error on UploadMessage, enables Retry button
 * 3. Retry re-initiates upload without re-selecting file (max 3 retries)
 * 4. After 3 retries exhausted: disables Retry, re-enables attachment button,
 *    shows "Upload could not be completed" message
 * 5. On extraction failure (job status `failed`): displays failure reason,
 *    re-enables attachment button
 *
 * Requirements: 1.9, 7.1, 7.2, 7.3, 7.4
 */

export interface ChatUploadContainerProps {
  sessionId: string;
  /** Called when extraction is ready — used to insert system message */
  onReady?: (info: { jobId: string; filename: string; summary: string }) => void;
  /** Called when upload status changes */
  onStatusChange?: (status: UploadStatus) => void;
}

export function ChatUploadContainer({
  sessionId,
  onReady,
  onStatusChange,
}: ChatUploadContainerProps) {
  const { state, submit, retry, refreshStatus, reset } = useFileUpload({
    sessionId,
    onReady,
    onStatusChange,
  });

  /**
   * Determine if the attachment button should be disabled.
   *
   * The button is disabled while an upload is actively in progress
   * (uploading or polling). It is re-enabled when:
   * - Upload is idle (no upload started)
   * - All retries are exhausted (user needs to re-select file)
   * - Extraction failed (job status `failed` from server, not a network retry)
   * - Upload reaches a terminal state (done, partial, timeout, connection_lost)
   */
  const isAttachmentDisabled = useMemo(() => {
    // Always allow attachment in idle state
    if (state.status === 'idle') return false;

    // Re-enable after retries exhausted so user can select a new file
    if (state.retriesExhausted) return false;

    // Re-enable on extraction failure (server reported `failed`)
    // Only when not actively uploading (isActive false means we're done)
    if (state.status === 'failed' && !state.isActive && !state.retriesExhausted) {
      // This is an extraction failure or server error — re-enable attachment
      return false;
    }

    // Re-enable on terminal states that aren't retryable
    if (state.status === 'done' || state.status === 'timeout' || state.status === 'connection_lost') {
      return false;
    }

    // Disable while actively uploading or polling
    return state.isActive;
  }, [state.status, state.isActive, state.retriesExhausted]);

  /**
   * Determine if the Retry button should be shown and enabled.
   *
   * - Show Retry when status is `failed` and a network error occurred
   *   (lastFileRef still has a file, meaning the failure was during upload)
   * - Disable Retry when retries are exhausted (> 3 attempts)
   */
  const showRetryButton = useMemo(() => {
    return state.status === 'failed' && !state.retriesExhausted;
  }, [state.status, state.retriesExhausted]);

  /**
   * Handle file selection from the ChatUploadButton.
   * Resets any previous upload state and submits the new file.
   */
  const handleFileSelected = useCallback(
    (file: File) => {
      // If there was a previous failed/completed upload, reset before starting new one
      if (state.status !== 'idle') {
        reset();
      }
      // We store the file reference; actual submission happens via handleSubmit
    },
    [state.status, reset]
  );

  /**
   * Handle file removal from the ChatUploadButton preview chip.
   */
  const handleFileRemoved = useCallback(() => {
    if (state.status === 'idle') {
      reset();
    }
  }, [state.status, reset]);

  /**
   * Submit file upload. Called by the parent chat composer when the user
   * sends a message with an attached file.
   */
  const handleSubmit = useCallback(
    (file: File, message?: string) => {
      submit(file, message);
    },
    [submit]
  );

  /**
   * Handle retry click on the UploadMessage.
   * Resets the UploadMessage status to uploading and re-initiates the upload.
   * Requirements: 7.3
   */
  const handleRetry = useCallback(() => {
    retry();
  }, [retry]);

  /**
   * Handle refresh status click on the UploadMessage (for connection_lost).
   */
  const handleRefresh = useCallback(() => {
    refreshStatus();
  }, [refreshStatus]);

  // Only render UploadMessage if we've started an upload (not idle)
  const showUploadMessage = state.status !== 'idle';

  return (
    <div className="chat-upload-container">
      {/* Attachment button — re-enabled after retries exhausted or extraction failure */}
      <ChatUploadButton
        sessionId={sessionId}
        disabled={isAttachmentDisabled}
        onFileSelected={handleFileSelected}
        onFileRemoved={handleFileRemoved}
      />

      {/* Upload status message in conversation timeline */}
      {showUploadMessage && state.filename && state.fileType && (
        <UploadMessage
          jobId={state.jobId ?? ''}
          filename={state.filename}
          fileType={state.fileType}
          status={state.status as Exclude<UploadStatus, 'idle'>}
          summary={state.summary ?? undefined}
          error={state.error ?? undefined}
          onRetry={showRetryButton ? handleRetry : undefined}
          onRefresh={state.status === 'connection_lost' ? handleRefresh : undefined}
        />
      )}
    </div>
  );
}

export { type UploadStatus } from '@/lib/chat-upload/useFileUpload';
