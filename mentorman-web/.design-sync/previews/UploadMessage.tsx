import React from 'react';
import { UploadMessage } from 'mentorman-web';

// A timeline entry representing a file upload. `status` is the variant axis:
// it drives the badge colour, and several statuses add their own detail row,
// progress bar, or action button.

const noop = () => {};

/** The status axis end to end — this is the card to look at first. */
export function AllStatuses() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 520 }}>
      <UploadMessage jobId="j1" filename="learning-reflection.pdf" fileType="resume" status="uploading" />
      <UploadMessage jobId="j2" filename="q3-goals.md" fileType="resume" status="pending" />
      <UploadMessage jobId="j3" filename="q3-goals.md" fileType="resume" status="processing" />
      <UploadMessage
        jobId="j4"
        filename="learning-reflection.pdf"
        fileType="resume"
        status="ready"
        summary="Extracted three preferences about explanation style and pacing."
      />
      <UploadMessage jobId="j5" filename="q3-goals.md" fileType="resume" status="done" />
    </div>
  );
}

/** Uploading — the only status with an indeterminate progress bar. */
export function Uploading() {
  return (
    <div style={{ maxWidth: 520 }}>
      <UploadMessage jobId="j1" filename="learning-reflection.pdf" fileType="resume" status="uploading" />
    </div>
  );
}

/** Ready with an extraction summary (truncated past 80 chars by the component). */
export function ReadyWithSummary() {
  return (
    <div style={{ maxWidth: 520 }}>
      <UploadMessage
        jobId="j4"
        filename="learning-reflection.pdf"
        fileType="resume"
        status="ready"
        summary="Extracted three preferences about explanation style, pacing, and how you like to be corrected mid-answer."
      />
    </div>
  );
}

/** The problem statuses, each with its own detail row and action. */
export function ProblemStates() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 520 }}>
      <UploadMessage jobId="j6" filename="slides.key" fileType="resume" status="partial" />
      <UploadMessage
        jobId="j7"
        filename="scanned-notes.pdf"
        fileType="resume"
        status="failed"
        error="No extractable text layer — try exporting as a text PDF."
        onRetry={noop}
      />
      <UploadMessage jobId="j8" filename="big-export.csv" fileType="resume" status="timeout" />
      <UploadMessage jobId="j9" filename="submissions.json" fileType="leetcode" status="connection_lost" onRefresh={noop} />
    </div>
  );
}

/** fileType picks the glyph — doc for resume, code for leetcode. */
export function FileTypes() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 520 }}>
      <UploadMessage jobId="j10" filename="learning-reflection.pdf" fileType="resume" status="done" />
      <UploadMessage jobId="j11" filename="leetcode-submissions.json" fileType="leetcode" status="done" />
    </div>
  );
}
