/**
 * API client for the document upload pipeline.
 *
 * Provides the `uploadDocuments` function that sends valid files, the
 * skip_review flag, and an optional message to `POST /api/documents/upload`
 * as multipart/form-data.
 *
 * Requirements: 1.5, 5.7, 5.9
 */

export interface UploadDocumentsPayload {
  /** Only valid files (those not flagged with errors). */
  files: File[];
  /** When true, extracted facts are written directly to L1 without PendingChanges. */
  skipReview: boolean;
  /** Optional accompanying text message. */
  message?: string;
}

export interface UploadDocumentsResponse {
  /** Upload job ID for polling status. */
  jobId: string;
  /** Number of files accepted by the server. */
  acceptedFiles: number;
  /** Files rejected server-side with reasons. */
  rejectedFiles: Array<{ filename: string; reason: string }>;
}

export interface UploadDocumentsError {
  /** Error type: 'validation' for 400, 'auth' for 401, 'network' for network failures. */
  type: 'validation' | 'auth' | 'network' | 'server';
  /** Human-readable error message. */
  message: string;
  /** Per-file errors (when type is 'validation'). */
  errors?: Array<{ filename: string; reason: string }>;
}

export interface RetryAnalysisResponse {
  /** Updated job ID (may be same or new). */
  jobId: string;
  /** Status after initiating retry. */
  status: string;
}

/**
 * Calls `POST /api/documents/jobs/{jobId}/retry-analysis` to re-run LLM
 * synthesis using preserved extracted text (when extraction succeeded
 * but synthesis failed).
 *
 * Requirements: 9.5, 9.6
 *
 * @returns On success, resolves with the response body.
 * @throws On failure, rejects with an UploadDocumentsError.
 */
export async function retryAnalysis(jobId: string): Promise<RetryAnalysisResponse> {
  let response: Response;
  try {
    response = await fetch(`/api/documents/jobs/${jobId}/retry-analysis`, {
      method: 'POST',
    });
  } catch {
    throw {
      type: 'network',
      message: 'Could not reach the server to retry analysis.',
    } satisfies UploadDocumentsError;
  }

  if (response.ok) {
    const data = await response.json();
    return {
      jobId: data.jobId ?? data.job_id ?? jobId,
      status: data.status ?? 'synthesizing',
    };
  }

  if (response.status === 400) {
    const data = await response.json().catch(() => ({ detail: 'Retry not available' }));
    throw {
      type: 'validation',
      message: data.detail ?? 'Retry analysis is not available for this job.',
    } satisfies UploadDocumentsError;
  }

  if (response.status === 401) {
    throw {
      type: 'auth',
      message: 'Authentication required. Please sign in again.',
    } satisfies UploadDocumentsError;
  }

  throw {
    type: 'server',
    message: `Retry failed (HTTP ${response.status})`,
  } satisfies UploadDocumentsError;
}

/**
 * Uploads documents to `POST /api/documents/upload` as multipart/form-data.
 *
 * @returns On success (HTTP 202), resolves with the response body.
 * @throws On failure, rejects with an UploadDocumentsError.
 */
export async function uploadDocuments(
  payload: UploadDocumentsPayload
): Promise<UploadDocumentsResponse> {
  const { files, skipReview, message } = payload;

  const formData = new FormData();

  // Append each valid file under the 'files' field
  for (const file of files) {
    formData.append('files', file);
  }

  // Append skip_review flag
  formData.append('skip_review', String(skipReview));

  // Append optional message
  if (message) {
    formData.append('message', message);
  }

  let response: Response;
  try {
    response = await fetch('/api/documents/upload', {
      method: 'POST',
      body: formData,
    });
  } catch {
    throw {
      type: 'network',
      message: 'Upload could not be completed due to a network issue.',
    } satisfies UploadDocumentsError;
  }

  if (response.status === 202) {
    const data = await response.json();
    return {
      jobId: data.jobId ?? data.job_id,
      acceptedFiles: data.acceptedFiles ?? data.accepted_files ?? 0,
      rejectedFiles: data.rejectedFiles ?? data.rejected_files ?? [],
    };
  }

  if (response.status === 401) {
    throw {
      type: 'auth',
      message: 'Authentication required. Please sign in again.',
    } satisfies UploadDocumentsError;
  }

  if (response.status === 400) {
    const data = await response.json().catch(() => ({ detail: { message: 'Validation failed' } }));
    const detail = data.detail ?? data;
    throw {
      type: 'validation',
      message: detail.message ?? 'All files failed validation',
      errors: detail.errors ?? [],
    } satisfies UploadDocumentsError;
  }

  // Other server errors
  throw {
    type: 'server',
    message: `Upload failed (HTTP ${response.status})`,
  } satisfies UploadDocumentsError;
}
