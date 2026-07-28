'use client';

/**
 * useDocumentUploadFlow — custom hook orchestrating the full document upload
 * pipeline from file submission through proposal resolution.
 *
 * Flow:
 * 1. User submits files via ChatDocumentUploader.onSubmit
 * 2. Calls uploadDocuments() from the API client → receives jobId (or error)
 * 3. On success (202): transitions to 'polling' phase with the jobId
 * 4. UploadStatusIndicator polls until terminal state
 * 5. On 'done' with proposals: transitions to 'proposals' phase
 * 6. On 'done' without proposals: transitions to 'no_proposals' phase
 * 7. On 'failed': transitions to 'failed' phase with error details
 * 8. User accepts/dismisses proposals via pending-changes endpoints
 * 9. Chat remains fully functional (non-blocking) throughout
 *
 * Requirements: 5.3, 6.1, 9.3
 */

import { useState, useCallback, useRef } from 'react';
import {
  uploadDocuments,
  retryAnalysis,
  type UploadDocumentsPayload,
  type UploadDocumentsResponse,
  type UploadDocumentsError,
} from './document-upload-api';
import type { Proposal, FailedFile } from '@/components/mentorman/chat/DocumentProposalCard';
import type { JobStatusResponse } from '@/components/mentorman/chat/UploadStatusIndicator';

// ─── Types ────────────────────────────────────────────────────────────────────

export type DocumentUploadPhase =
  | 'idle'
  | 'uploading'
  | 'polling'
  | 'proposals'
  | 'no_proposals'
  | 'failed'
  | 'network_error';

export interface DocumentUploadFlowState {
  phase: DocumentUploadPhase;
  jobId: string | null;
  /** Whether skip review was enabled for this upload. */
  skipReview: boolean;
  /** Proposals returned by the backend (when phase is 'proposals'). */
  proposals: Proposal[];
  /** Files that failed extraction (shown alongside proposals or in error state). */
  failedFiles: FailedFile[];
  /** Network error message (when phase is 'network_error'). */
  networkError: string | null;
  /** Number of consecutive network failures for retry logic. */
  consecutiveFailures: number;
  /** Files that were submitted (kept for retry). */
  submittedFiles: File[];
  /** Message text (kept for retry). */
  submittedMessage?: string;
}

export interface UseDocumentUploadFlowReturn {
  state: DocumentUploadFlowState;
  /** Called by ChatDocumentUploader.onSubmit to start the upload flow. */
  submitUpload: (payload: UploadDocumentsPayload) => Promise<void>;
  /** Called by UploadStatusIndicator.onDone when job reaches 'done'. */
  handleJobDone: (data: JobStatusResponse) => void;
  /** Called by UploadStatusIndicator.onFailed when job reaches 'failed'. */
  handleJobFailed: (data: JobStatusResponse) => void;
  /** Accept a proposal by calling the pending-changes endpoint. */
  acceptProposal: (proposalId: string) => Promise<void>;
  /** Dismiss a proposal by calling the pending-changes endpoint. */
  dismissProposal: (proposalId: string) => Promise<void>;
  /** Accept all pending proposals. */
  acceptAllProposals: () => Promise<void>;
  /** Retry the upload after a network failure. */
  retryUpload: () => Promise<void>;
  /** Retry analysis for a failed job (re-runs synthesis). */
  retryJobAnalysis: () => Promise<void>;
  /** Reset back to idle state. */
  reset: () => void;
}

const MAX_CONSECUTIVE_FAILURES = 3;

const INITIAL_STATE: DocumentUploadFlowState = {
  phase: 'idle',
  jobId: null,
  skipReview: false,
  proposals: [],
  failedFiles: [],
  networkError: null,
  consecutiveFailures: 0,
  submittedFiles: [],
  submittedMessage: undefined,
};

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useDocumentUploadFlow(): UseDocumentUploadFlowReturn {
  const [state, setState] = useState<DocumentUploadFlowState>(INITIAL_STATE);
  const consecutiveFailuresRef = useRef(0);

  /**
   * Submit files for upload. Calls POST /api/documents/upload.
   * On 202, moves to 'polling' phase.
   * On error, moves to 'network_error' or stays 'idle' depending on error type.
   */
  const submitUpload = useCallback(async (payload: UploadDocumentsPayload) => {
    const { files, skipReview, message } = payload;

    // Store for retry
    setState((prev) => ({
      ...prev,
      phase: 'uploading',
      jobId: null,
      skipReview,
      proposals: [],
      failedFiles: [],
      networkError: null,
      submittedFiles: files,
      submittedMessage: message,
    }));

    try {
      const response: UploadDocumentsResponse = await uploadDocuments(payload);

      // Success — move to polling phase
      setState((prev) => ({
        ...prev,
        phase: 'polling',
        jobId: response.jobId,
        consecutiveFailures: 0,
      }));
      consecutiveFailuresRef.current = 0;
    } catch (err: unknown) {
      const error = err as UploadDocumentsError;

      if (error.type === 'network') {
        consecutiveFailuresRef.current += 1;
        const exhausted = consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES;

        setState((prev) => ({
          ...prev,
          phase: 'network_error',
          networkError: error.message,
          consecutiveFailures: consecutiveFailuresRef.current,
        }));
      } else {
        // Validation or auth error — show as failed (not retryable via network retry)
        setState((prev) => ({
          ...prev,
          phase: 'failed',
          networkError: error.message,
          failedFiles: error.errors?.map((e) => ({
            filename: e.filename,
            reason: e.reason,
          })) ?? [],
        }));
      }
    }
  }, []);

  /**
   * Called when UploadStatusIndicator reports the job is done.
   * Transitions to 'proposals' or 'no_proposals' phase.
   */
  const handleJobDone = useCallback((data: JobStatusResponse) => {
    const proposals: Proposal[] = Array.isArray(data.proposals)
      ? data.proposals.map((p: any, idx: number) => ({
          id: p.id ?? `proposal-${idx}`,
          field: p.field,
          proposedValue: p.proposedValue ?? p.proposed_value ?? {},
          reason: p.reason ?? '',
          sourceFilename: p.sourceFilename ?? p.source_filename ?? '',
          status: 'pending' as const,
          requires_replacement: p.requires_replacement ?? false,
        }))
      : [];

    const failedFiles: FailedFile[] = Array.isArray(data.failedFiles)
      ? data.failedFiles
      : [];

    if (proposals.length === 0) {
      setState((prev) => ({
        ...prev,
        phase: 'no_proposals',
        proposals: [],
        failedFiles,
      }));
    } else {
      setState((prev) => ({
        ...prev,
        phase: 'proposals',
        proposals,
        failedFiles,
      }));
    }
  }, []);

  /**
   * Called when UploadStatusIndicator reports the job has failed.
   */
  const handleJobFailed = useCallback((data: JobStatusResponse) => {
    const failedFiles: FailedFile[] = Array.isArray(data.failedFiles)
      ? data.failedFiles
      : [];

    setState((prev) => ({
      ...prev,
      phase: 'failed',
      failedFiles,
      networkError: null,
    }));
  }, []);

  /**
   * Accept a proposal by calling POST /api/profile/pending-changes/{field}/accept.
   * Updates the local proposal status optimistically.
   */
  const acceptProposal = useCallback(async (proposalId: string) => {
    // Find the proposal to get its field
    setState((prev) => {
      const proposal = prev.proposals.find((p) => p.id === proposalId);
      if (!proposal) return prev;

      return {
        ...prev,
        proposals: prev.proposals.map((p) =>
          p.id === proposalId ? { ...p, status: 'accepted' as const } : p
        ),
      };
    });

    // Get the proposal field for the API call
    const proposal = state.proposals.find((p) => p.id === proposalId);
    if (!proposal) return;

    try {
      await fetch(`/api/profile/pending-changes/${proposal.field}/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposal_id: proposalId }),
      });
    } catch {
      // Revert on failure
      setState((prev) => ({
        ...prev,
        proposals: prev.proposals.map((p) =>
          p.id === proposalId ? { ...p, status: 'pending' as const } : p
        ),
      }));
    }
  }, [state.proposals]);

  /**
   * Dismiss a proposal by calling POST /api/profile/pending-changes/{field}/dismiss.
   * Updates the local proposal status optimistically.
   */
  const dismissProposal = useCallback(async (proposalId: string) => {
    setState((prev) => {
      const proposal = prev.proposals.find((p) => p.id === proposalId);
      if (!proposal) return prev;

      return {
        ...prev,
        proposals: prev.proposals.map((p) =>
          p.id === proposalId ? { ...p, status: 'dismissed' as const } : p
        ),
      };
    });

    const proposal = state.proposals.find((p) => p.id === proposalId);
    if (!proposal) return;

    try {
      await fetch(`/api/profile/pending-changes/${proposal.field}/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proposal_id: proposalId }),
      });
    } catch {
      // Revert on failure
      setState((prev) => ({
        ...prev,
        proposals: prev.proposals.map((p) =>
          p.id === proposalId ? { ...p, status: 'pending' as const } : p
        ),
      }));
    }
  }, [state.proposals]);

  /**
   * Accept all pending proposals in one batch.
   */
  const acceptAllProposals = useCallback(async () => {
    const pendingProposals = state.proposals.filter((p) => p.status === 'pending');

    // Optimistically mark all as accepted
    setState((prev) => ({
      ...prev,
      proposals: prev.proposals.map((p) =>
        p.status === 'pending' ? { ...p, status: 'accepted' as const } : p
      ),
    }));

    // Fire all accept calls in parallel
    const results = await Promise.allSettled(
      pendingProposals.map((p) =>
        fetch(`/api/profile/pending-changes/${p.field}/accept`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ proposal_id: p.id }),
        })
      )
    );

    // Revert any that failed
    const failedIds = new Set<string>();
    results.forEach((result, idx) => {
      if (result.status === 'rejected' || (result.status === 'fulfilled' && !result.value.ok)) {
        failedIds.add(pendingProposals[idx].id);
      }
    });

    if (failedIds.size > 0) {
      setState((prev) => ({
        ...prev,
        proposals: prev.proposals.map((p) =>
          failedIds.has(p.id) ? { ...p, status: 'pending' as const } : p
        ),
      }));
    }
  }, [state.proposals]);

  /**
   * Retry the upload after a network failure.
   * Re-uses the previously submitted files.
   */
  const retryUpload = useCallback(async () => {
    if (state.submittedFiles.length === 0) return;
    if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES) return;

    await submitUpload({
      files: state.submittedFiles,
      skipReview: state.skipReview,
      message: state.submittedMessage,
    });
  }, [state.submittedFiles, state.skipReview, state.submittedMessage, submitUpload]);

  /**
   * Retry the LLM analysis for a failed job.
   * Calls POST /api/documents/jobs/{jobId}/retry-analysis.
   */
  const retryJobAnalysis = useCallback(async () => {
    if (!state.jobId) return;

    try {
      await retryAnalysis(state.jobId);
      // Move back to polling phase — UploadStatusIndicator will pick up the new status
      setState((prev) => ({
        ...prev,
        phase: 'polling',
        failedFiles: [],
        networkError: null,
      }));
    } catch {
      // Retry failed — leave in 'failed' state
    }
  }, [state.jobId]);

  /**
   * Reset everything back to idle.
   */
  const reset = useCallback(() => {
    consecutiveFailuresRef.current = 0;
    setState(INITIAL_STATE);
  }, []);

  return {
    state,
    submitUpload,
    handleJobDone,
    handleJobFailed,
    acceptProposal,
    dismissProposal,
    acceptAllProposals,
    retryUpload,
    retryJobAnalysis,
    reset,
  };
}
