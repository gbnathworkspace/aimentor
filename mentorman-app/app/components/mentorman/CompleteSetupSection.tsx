'use client';

import React from 'react';

export interface CompleteSetupSectionProps {
  onStartSetup: () => void;
}

/**
 * A call-to-action section for the Settings page, shown only when
 * profile_status is "skipped". Encourages the user to complete their
 * onboarding setup for personalized mentoring.
 *
 * The parent component is responsible for conditionally rendering this
 * section based on `profile_status`.
 */
export function CompleteSetupSection({ onStartSetup }: CompleteSetupSectionProps) {
  return (
    <div className="set-section" data-testid="complete-setup-section">
      <div className="set-label">Complete Your Profile</div>
      <div className="complete-setup-card" style={{
        padding: '16px',
        background: 'var(--card-2, rgba(255,255,255,0.03))',
        borderRadius: 8,
        border: '1px solid var(--border, rgba(255,255,255,0.06))',
      }}>
        <p style={{
          fontSize: 13,
          color: 'var(--muted)',
          margin: '0 0 12px 0',
          lineHeight: 1.5,
        }}>
          Complete your profile to get personalized study plans, skill tracking, and tailored mentoring advice.
        </p>
        <button
          className="btn btn-accent"
          onClick={onStartSetup}
          type="button"
          style={{ width: '100%', height: 40 }}
        >
          Complete Setup
        </button>
      </div>
    </div>
  );
}
