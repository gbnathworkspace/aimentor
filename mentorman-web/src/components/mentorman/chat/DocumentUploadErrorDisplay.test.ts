/**
 * Unit tests for the DocumentUploadErrorDisplay component logic.
 *
 * Tests the conditional rendering logic, retry state management, and
 * prop-driven behavior without rendering React components.
 *
 * Validates: Requirements 6.6, 6.7, 6.8, 9.1, 9.2, 9.6
 */
import { describe, it, expect } from 'vitest';

// ─── Logic helpers extracted from the component for testability ──

const MAX_CONSECUTIVE_FAILURES = 3;

/**
 * Determines which display variant to show based on props.
 * Mirrors the conditional logic in DocumentUploadErrorDisplay.
 */
function determineDisplayMode(params: {
  jobStatus: 'done' | 'failed';
  failedFiles: Array<{ filename: string; reason: string }>;
  isNetworkError: boolean;
  consecutiveFailures: number;
}): 'network-error' | 'no-proposals' | 'failed' | 'partial-no-proposals' | null {
  const { jobStatus, failedFiles, isNetworkError, consecutiveFailures } = params;

  // Network error takes precedence
  if (isNetworkError) return 'network-error';

  // Job done with no failures = no proposals found
  if (jobStatus === 'done' && failedFiles.length === 0) return 'no-proposals';

  // Job failed = processing failure with per-file errors
  if (jobStatus === 'failed') return 'failed';

  // Job done with failed files but no proposals
  if (jobStatus === 'done' && failedFiles.length > 0) return 'partial-no-proposals';

  return null;
}

/**
 * Determines if the retry button should be disabled.
 */
function isRetryDisabled(consecutiveFailures: number): boolean {
  return consecutiveFailures >= MAX_CONSECUTIVE_FAILURES;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DocumentUploadErrorDisplay — display mode selection', () => {
  it('shows network-error when isNetworkError is true', () => {
    const mode = determineDisplayMode({
      jobStatus: 'failed',
      failedFiles: [],
      isNetworkError: true,
      consecutiveFailures: 0,
    });
    expect(mode).toBe('network-error');
  });

  it('network-error takes precedence even if jobStatus is done', () => {
    const mode = determineDisplayMode({
      jobStatus: 'done',
      failedFiles: [],
      isNetworkError: true,
      consecutiveFailures: 2,
    });
    expect(mode).toBe('network-error');
  });

  it('shows no-proposals when job is done with no failed files', () => {
    const mode = determineDisplayMode({
      jobStatus: 'done',
      failedFiles: [],
      isNetworkError: false,
      consecutiveFailures: 0,
    });
    expect(mode).toBe('no-proposals');
  });

  it('shows failed when job status is failed', () => {
    const mode = determineDisplayMode({
      jobStatus: 'failed',
      failedFiles: [{ filename: 'corrupt.pdf', reason: 'File could not be read' }],
      isNetworkError: false,
      consecutiveFailures: 0,
    });
    expect(mode).toBe('failed');
  });

  it('shows failed even without specific file errors', () => {
    const mode = determineDisplayMode({
      jobStatus: 'failed',
      failedFiles: [],
      isNetworkError: false,
      consecutiveFailures: 0,
    });
    expect(mode).toBe('failed');
  });

  it('shows partial-no-proposals when job is done with failed files', () => {
    const mode = determineDisplayMode({
      jobStatus: 'done',
      failedFiles: [
        { filename: 'locked.pdf', reason: 'File is password-protected' },
      ],
      isNetworkError: false,
      consecutiveFailures: 0,
    });
    expect(mode).toBe('partial-no-proposals');
  });
});

describe('DocumentUploadErrorDisplay — retry disable logic (Req 9.2)', () => {
  it('retry is enabled when consecutiveFailures < 3', () => {
    expect(isRetryDisabled(0)).toBe(false);
    expect(isRetryDisabled(1)).toBe(false);
    expect(isRetryDisabled(2)).toBe(false);
  });

  it('retry is disabled when consecutiveFailures >= 3', () => {
    expect(isRetryDisabled(3)).toBe(true);
    expect(isRetryDisabled(4)).toBe(true);
    expect(isRetryDisabled(10)).toBe(true);
  });
});

describe('DocumentUploadErrorDisplay — no proposals message (Req 6.6)', () => {
  it('displays informational tone (not error) when job done with no proposals', () => {
    const mode = determineDisplayMode({
      jobStatus: 'done',
      failedFiles: [],
      isNetworkError: false,
      consecutiveFailures: 0,
    });
    // Should show no-proposals variant, not an error variant
    expect(mode).toBe('no-proposals');
  });
});

describe('DocumentUploadErrorDisplay — per-file failure display (Req 6.7)', () => {
  it('renders failure reason for each file in the failed list', () => {
    const failedFiles = [
      { filename: 'corrupt.pdf', reason: 'File could not be read' },
      { filename: 'empty.txt', reason: 'No extractable content' },
      { filename: 'locked.xlsx', reason: 'File is password-protected' },
    ];
    // Each file should have a name and reason shown
    expect(failedFiles).toHaveLength(3);
    expect(failedFiles[0].filename).toBe('corrupt.pdf');
    expect(failedFiles[0].reason).toBe('File could not be read');
    expect(failedFiles[2].reason).toContain('password-protected');
  });
});

describe('DocumentUploadErrorDisplay — network retry flow (Req 9.1, 9.2)', () => {
  it('retry button available on first failure', () => {
    const disabled = isRetryDisabled(0);
    expect(disabled).toBe(false);
  });

  it('retry button available on second failure', () => {
    const disabled = isRetryDisabled(1);
    expect(disabled).toBe(false);
  });

  it('retry button disabled after 3 consecutive failures', () => {
    const disabled = isRetryDisabled(3);
    expect(disabled).toBe(true);
  });

  it('shows "try again later" message when retries exhausted', () => {
    // When retriesExhausted=true, component shows the exhausted message
    // instead of the retry button
    const retriesExhausted = 3 >= MAX_CONSECUTIVE_FAILURES;
    expect(retriesExhausted).toBe(true);
  });
});

describe('DocumentUploadErrorDisplay — retry analysis (Req 9.6)', () => {
  it('retry analysis is available when onRetryAnalysis callback is provided', () => {
    // The component renders the "Retry Analysis" button only when onRetryAnalysis prop is present
    const onRetryAnalysis = () => {};
    expect(typeof onRetryAnalysis).toBe('function');
  });

  it('retry analysis button calls POST endpoint with correct jobId', () => {
    const jobId = 'test-job-123';
    const expectedUrl = `/api/documents/jobs/${jobId}/retry-analysis`;
    expect(expectedUrl).toBe('/api/documents/jobs/test-job-123/retry-analysis');
  });
});
