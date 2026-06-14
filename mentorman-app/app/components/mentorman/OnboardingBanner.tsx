'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';

export interface OnboardingBannerProps {
  onComplete: () => void;
  onDismiss: () => void;
}

const STORAGE_KEY = 'mentorman_banner_dismissed';

/**
 * Check if banner was previously dismissed in this browser session.
 * Returns false (show banner) if sessionStorage is unavailable or throws.
 */
function isDismissedInSession(): boolean {
  try {
    return sessionStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    // sessionStorage unavailable (e.g., private browsing quirks) — always show banner
    return false;
  }
}

/**
 * Persist banner dismissal in sessionStorage.
 * Fails silently if storage is unavailable.
 */
function persistDismissal(): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, 'true');
  } catch {
    // Gracefully ignore — banner just won't persist across refreshes
  }
}

/**
 * A non-overlapping banner displayed above the chat message area for users
 * who skipped onboarding. Encourages them to complete their profile setup.
 *
 * - Message: "Complete your profile to get personalized study plans and skill tracking."
 * - "Complete Setup" link navigates to deferred onboarding
 * - Dismiss button hides banner for the browser session (sessionStorage)
 * - Handles sessionStorage unavailability gracefully (always shows if storage throws)
 */
export function OnboardingBanner({ onComplete, onDismiss }: OnboardingBannerProps) {
  const [dismissed, setDismissed] = useState<boolean | null>(null);

  useEffect(() => {
    setDismissed(isDismissedInSession());
  }, []);

  // While checking sessionStorage (SSR/initial render), render nothing
  if (dismissed === null || dismissed === true) {
    return null;
  }

  const handleDismiss = () => {
    persistDismissal();
    setDismissed(true);
    onDismiss();
  };

  return (
    <div className="onboarding-banner" role="banner" aria-label="Complete onboarding reminder">
      <div className="onboarding-banner-content">
        <span className="onboarding-banner-text">
          Complete your profile to get personalized study plans and skill tracking.
        </span>
        <button
          className="onboarding-banner-link"
          onClick={onComplete}
          type="button"
        >
          Complete Setup
        </button>
      </div>
      <button
        className="onboarding-banner-dismiss"
        onClick={handleDismiss}
        aria-label="Dismiss banner"
        type="button"
        title="Dismiss"
      >
        <Icon name="x" size={14} />
      </button>
    </div>
  );
}
