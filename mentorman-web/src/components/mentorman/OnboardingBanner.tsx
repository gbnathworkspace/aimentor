import React, { useState, useEffect } from 'react';
import { Icon } from './icons';

export interface OnboardingBannerProps {
  onComplete: () => void;
  onDismiss: () => void;
}

const STORAGE_KEY = 'mentorman_banner_dismissed';

function isDismissedInSession(): boolean {
  try { return sessionStorage.getItem(STORAGE_KEY) === 'true'; } catch { return false; }
}

function persistDismissal(): void {
  try { sessionStorage.setItem(STORAGE_KEY, 'true'); } catch { /* ignore */ }
}

export function OnboardingBanner({ onComplete, onDismiss }: OnboardingBannerProps) {
  const [dismissed, setDismissed] = useState<boolean | null>(null);

  useEffect(() => { setDismissed(isDismissedInSession()); }, []);

  if (dismissed === null || dismissed === true) return null;

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
        <button className="onboarding-banner-link" onClick={onComplete} type="button">
          Complete Setup
        </button>
      </div>
      <button className="onboarding-banner-dismiss" onClick={handleDismiss} aria-label="Dismiss banner" type="button" title="Dismiss">
        <Icon name="x" size={14} />
      </button>
    </div>
  );
}
