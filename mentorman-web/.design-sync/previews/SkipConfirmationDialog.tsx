import React from 'react';
import { SkipConfirmationDialog } from 'mentorman-web';

// A modal alertdialog confirming the user wants to skip profile setup. It is a
// fixed-position overlay, so cfg.overrides.SkipConfirmationDialog pins it to a
// single full-card render — see .design-sync/config.json.

const noop = () => {};

/** Open, idle — the state the user first sees. */
export function Open() {
  return <SkipConfirmationDialog open onConfirm={noop} onCancel={noop} />;
}

/** Mid-request: both actions disabled, the confirm button shows progress copy. */
export function Loading() {
  return <SkipConfirmationDialog open loading onConfirm={noop} onCancel={noop} />;
}

/** The skip request failed — an inline alert appears above the actions. */
export function WithError() {
  return (
    <SkipConfirmationDialog
      open
      error="Couldn't save that — check your connection and try again."
      onConfirm={noop}
      onCancel={noop}
    />
  );
}
