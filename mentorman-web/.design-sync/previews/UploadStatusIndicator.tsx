import React from 'react';
import { UploadStatusIndicator } from 'mentorman-web';

// Spinner + stage label shown while a document job processes. The component
// polls GET /api/documents/jobs/{jobId}/status and derives its own status, so
// only the initial "pending" stage renders statically — the later stages are
// server-driven and cannot be forced from props. It renders null once terminal.

/** The pending stage — "Uploading files…" with the spinner. */
export function Default() {
  return (
    <div style={{ maxWidth: 460 }}>
      <UploadStatusIndicator jobId="job_8f2c" />
    </div>
  );
}

/** In the chat timeline, following the upload message it belongs to. */
export function InTimeline() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 520 }}>
      <div className="upload-message">
        <div className="upload-msg-header">
          <span className="upload-msg-filename">learning-reflection.pdf</span>
          <span className="upload-msg-badge info">Processing</span>
        </div>
      </div>
      <UploadStatusIndicator jobId="job_8f2c" />
    </div>
  );
}

/** Scaled up so the spinner and label treatment are legible in the card. */
export function Enlarged() {
  return (
    <div style={{ transform: 'scale(1.8)', transformOrigin: 'left top', width: 420 }}>
      <UploadStatusIndicator jobId="job_8f2c" />
    </div>
  );
}
