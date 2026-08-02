import React from 'react';
import { DocumentUploadErrorDisplay } from 'mentorman-web';

// The terminal-state card for a document job that produced nothing usable.
// It has four distinct branches keyed off jobStatus / isNetworkError /
// failedFiles — each is a separate cell below.

const noop = () => {};

const failed = [
  { filename: 'scanned-notes.pdf', reason: 'No extractable text layer' },
  { filename: 'slides.key', reason: 'Unsupported file type' },
];

/** Job completed but nothing profile-relevant was found. */
export function NoProposals() {
  return (
    <div style={{ maxWidth: 540 }}>
      <DocumentUploadErrorDisplay jobId="job_8f2c" jobStatus="done" onClose={noop} />
    </div>
  );
}

/** Processing failed — per-file reasons plus both retry actions. */
export function ProcessingFailed() {
  return (
    <div style={{ maxWidth: 540 }}>
      <DocumentUploadErrorDisplay
        jobId="job_1a90"
        jobStatus="failed"
        failedFiles={failed}
        onRetryUpload={noop}
        onRetryAnalysis={noop}
        onClose={noop}
      />
    </div>
  );
}

/** A network failure during upload, with retry still available. */
export function NetworkError() {
  return (
    <div style={{ maxWidth: 540 }}>
      <DocumentUploadErrorDisplay
        jobId="job_c7d3"
        jobStatus="failed"
        isNetworkError
        networkErrorMessage="Upload could not be completed — the connection dropped partway through."
        consecutiveFailures={1}
        onRetryUpload={noop}
        onClose={noop}
      />
    </div>
  );
}

/** Three consecutive network failures — retry is withdrawn entirely. */
export function RetriesExhausted() {
  return (
    <div style={{ maxWidth: 540 }}>
      <DocumentUploadErrorDisplay
        jobId="job_c7d3"
        jobStatus="failed"
        isNetworkError
        networkErrorMessage="Upload could not be completed due to a network issue."
        consecutiveFailures={3}
        onRetryUpload={noop}
        onClose={noop}
      />
    </div>
  );
}

/** Done, but some files failed — "Partial" badge and a failed-files list. */
export function PartialSuccess() {
  return (
    <div style={{ maxWidth: 540 }}>
      <DocumentUploadErrorDisplay
        jobId="job_44b1"
        jobStatus="done"
        failedFiles={failed}
        onRetryUpload={noop}
        onClose={noop}
      />
    </div>
  );
}
