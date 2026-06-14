'use client';

import React from 'react';

export interface SkipButtonProps {
  onSkip: () => void;
  disabled?: boolean;
}

/**
 * A text/outline-style skip button for the onboarding top navigation bar.
 * Visually subordinate to the main onboarding conversation flow.
 * Rendered inside the `.onb-top` container alongside the progress indicator.
 */
export function SkipButton({ onSkip, disabled = false }: SkipButtonProps) {
  return (
    <button
      className="btn btn-ghost btn-sm"
      onClick={onSkip}
      disabled={disabled}
      aria-label="Skip"
      type="button"
    >
      Skip
    </button>
  );
}
