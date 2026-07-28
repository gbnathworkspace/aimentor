'use client';

import React from 'react';
import { UploadStatusIndicator } from './UploadStatusIndicator';
import { DocumentProposalCard } from './DocumentProposalCard';
import { DocumentUploadErrorDisplay } from './DocumentUploadErrorDisplay';
import {
  useDocumentUploadFlow,
  type UseDocumentUploadFlowReturn,
} from '@/lib/chat-upload/useDocumentUploadFlow';
import type { StyleNote } from '@/lib/mentorman-api';
import type { JobStatusResponse } from './UploadStatusIndicator';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DocumentUploadFlowProps {
  /** The current session ID. */
  sessionId: string;
  /** Existing style notes from the user's profile (for replacement flow). */
  existingStyleNotes?: StyleNote[];
  /** Expose the flow controller for integration with ChatDocumentUploader. */
  flowRef?: React.MutableRefObject<UseDocumentUploadFlowReturn | null>;
}

/**
 * DocumentUploadFlow — container component that orchestrates the full document
 * upload lifecycle in the chat timeline.
 *
 * Renders the appropriate UI based on the current flow phase:
 * - 'idle': nothing rendered
 * - 'uploading': spinner (brief, transitions quickly to polling)
 * - 'polling': UploadStatusIndicator (polls every 2s)
 * - 'proposals': DocumentProposalCard (interactive accept/dismiss)
 * - 'no_proposals': DocumentUploadErrorDisplay (informational)
 * - 'failed': DocumentUploadErrorDisplay (with retry options)
 * - 'network_error': DocumentUploadErrorDisplay (network failure + retry)
 *
 * The chat session remains fully functional during all phases (non-blocking).
 * This component renders inline within the chat body — it does NOT block
 * the composer or message list.
 *
 * Requirements: 5.3, 6.1, 9.3
 */
export function DocumentUploadFlow({
  sessionId,
  existingStyleNotes,
  flowRef,
}: DocumentUploadFlowProps) {
  const flow = useDocumentUploadFlow();

  // Expose the flow controller to the parent so ChatDocumentUploader can trigger submitUpload
  if (flowRef) {
    flowRef.current = flow;
  }

  const { state } = flow;

  // ── Idle: nothing to render ──
  if (state.phase === 'idle') {
    return null;
  }

  // ── Uploading: brief loading indicator ──
  if (state.phase === 'uploading') {
    return (
      <div className="document-upload-flow" data-phase="uploading" data-session-id={sessionId}>
        <div className="upload-status-indicator" role="status" aria-live="polite">
          <span className="upload-status-spinner" aria-hidden="true" />
          <span className="upload-status-label">Uploading files...</span>
        </div>
      </div>
    );
  }

  // ── Polling: UploadStatusIndicator handles polling + stage labels ──
  if (state.phase === 'polling' && state.jobId) {
    return (
      <div className="document-upload-flow" data-phase="polling" data-session-id={sessionId}>
        <UploadStatusIndicator
          jobId={state.jobId}
          onDone={(data: JobStatusResponse) => flow.handleJobDone(data)}
          onFailed={(data: JobStatusResponse) => flow.handleJobFailed(data)}
        />
      </div>
    );
  }

  // ── Proposals: interactive card with accept/dismiss ──
  if (state.phase === 'proposals') {
    return (
      <div className="document-upload-flow" data-phase="proposals" data-session-id={sessionId}>
        <DocumentProposalCard
          jobId={state.jobId ?? ''}
          proposals={state.proposals}
          failedFiles={state.failedFiles.length > 0 ? state.failedFiles : undefined}
          skipReview={state.skipReview}
          existingStyleNotes={existingStyleNotes}
          onAccept={(proposalId) => flow.acceptProposal(proposalId)}
          onDismiss={(proposalId) => flow.dismissProposal(proposalId)}
          onAcceptAll={() => flow.acceptAllProposals()}
          onReplace={(proposalId, index) => {
            // Replace is handled the same as accept — backend handles the replacement logic
            flow.acceptProposal(proposalId);
          }}
          onClose={() => flow.reset()}
        />
      </div>
    );
  }

  // ── No proposals: informational message ──
  if (state.phase === 'no_proposals') {
    return (
      <div className="document-upload-flow" data-phase="no_proposals" data-session-id={sessionId}>
        <DocumentUploadErrorDisplay
          jobId={state.jobId ?? ''}
          jobStatus="done"
          failedFiles={state.failedFiles.length > 0 ? state.failedFiles : undefined}
          onRetryUpload={state.failedFiles.length > 0 ? () => flow.retryUpload() : undefined}
          onClose={() => flow.reset()}
        />
      </div>
    );
  }

  // ── Failed: error display with retry options ──
  if (state.phase === 'failed') {
    return (
      <div className="document-upload-flow" data-phase="failed" data-session-id={sessionId}>
        <DocumentUploadErrorDisplay
          jobId={state.jobId ?? ''}
          jobStatus="failed"
          failedFiles={state.failedFiles.length > 0 ? state.failedFiles : undefined}
          onRetryUpload={() => flow.retryUpload()}
          onRetryAnalysis={state.jobId ? () => flow.retryJobAnalysis() : undefined}
          onClose={() => flow.reset()}
        />
      </div>
    );
  }

  // ── Network error: upload failed before job creation ──
  if (state.phase === 'network_error') {
    return (
      <div className="document-upload-flow" data-phase="network_error" data-session-id={sessionId}>
        <DocumentUploadErrorDisplay
          jobId=""
          jobStatus="failed"
          isNetworkError={true}
          networkErrorMessage={state.networkError ?? undefined}
          consecutiveFailures={state.consecutiveFailures}
          onRetryUpload={() => flow.retryUpload()}
          onClose={() => flow.reset()}
        />
      </div>
    );
  }

  return null;
}
