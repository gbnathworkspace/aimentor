import React from 'react';
import { AttachmentPreview } from 'mentorman-web';

// Staged-file chips shown inside the composer box before sending. There is no
// submit here — the composer's Send picks the files up. It renders null when
// there are no files and no warning, so every cell supplies at least one.

const noop = () => {};

// FileValidationResult is { file: File, error: string | null }. Real File
// objects are built here so the chips show true sizes via formatFileSize.
function file(name: string, kb: number, type = 'application/pdf') {
  return new File([new Uint8Array(kb * 1024)], name, { type });
}

const staged = [
  { file: file('learning-reflection.pdf', 240), error: null },
  { file: file('q3-goals.md', 6, 'text/markdown'), error: null },
];

/** Two valid staged files with the Skip Review toggle and Clear all. */
export function Default() {
  return (
    <div className="composer-box" style={{ width: 560 }}>
      <AttachmentPreview
        fileResults={staged}
        warning={null}
        skipReview={false}
        onRemove={noop}
        onClearAll={noop}
        onToggleSkipReview={noop}
      />
    </div>
  );
}

/** Skip Review enabled — the toggle track and thumb move to the on state. */
export function SkipReviewOn() {
  return (
    <div className="composer-box" style={{ width: 560 }}>
      <AttachmentPreview
        fileResults={staged}
        warning={null}
        skipReview
        onRemove={noop}
        onClearAll={noop}
        onToggleSkipReview={noop}
      />
    </div>
  );
}

/** A rejected file — the chip takes the error modifier and shows the reason. */
export function WithFileError() {
  return (
    <div className="composer-box" style={{ width: 560 }}>
      <AttachmentPreview
        fileResults={[
          ...staged,
          { file: file('slides.key', 4200, 'application/octet-stream'), error: 'Unsupported file type' },
        ]}
        warning={null}
        skipReview={false}
        onRemove={noop}
        onClearAll={noop}
        onToggleSkipReview={noop}
      />
    </div>
  );
}

/** A batch-level warning above the chips. */
export function WithWarning() {
  return (
    <div className="composer-box" style={{ width: 560 }}>
      <AttachmentPreview
        fileResults={staged}
        warning="Only the first 5 files will be processed."
        skipReview={false}
        onRemove={noop}
        onClearAll={noop}
        onToggleSkipReview={noop}
      />
    </div>
  );
}

/** Disabled while a send is in flight — remove and clear controls go inert. */
export function Disabled() {
  return (
    <div className="composer-box" style={{ width: 560 }}>
      <AttachmentPreview
        fileResults={staged}
        warning={null}
        skipReview={false}
        disabled
        onRemove={noop}
        onClearAll={noop}
        onToggleSkipReview={noop}
      />
    </div>
  );
}
