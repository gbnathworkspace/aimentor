import React from 'react';

export interface SkipButtonProps {
  onSkip: () => void;
  disabled?: boolean;
}

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
