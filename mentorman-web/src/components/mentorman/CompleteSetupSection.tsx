import React from 'react';
import { Icon } from './icons';

export interface CompleteSetupSectionProps {
  onStartSetup: () => void;
  /** Shows a dismiss (×) button in the card's corner when provided. */
  onClose?: () => void;
}

export function CompleteSetupSection({ onStartSetup, onClose }: CompleteSetupSectionProps) {
  return (
    <div className="set-section" data-testid="complete-setup-section">
      <div className="set-label">Complete Your Profile</div>
      <div className="complete-setup-card" style={{
        position: 'relative',
        padding: '16px',
        background: 'var(--card-2, rgba(255,255,255,0.03))',
        borderRadius: 8,
        border: '1px solid var(--border, rgba(255,255,255,0.06))',
      }}>
        {onClose && (
          <button
            type="button"
            className="icon-btn"
            title="Dismiss"
            aria-label="Dismiss"
            onClick={onClose}
            style={{ position: 'absolute', top: 8, right: 8, width: 26, height: 26 }}
          >
            <Icon name="x" size={13} />
          </button>
        )}
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '0 0 12px 0', lineHeight: 1.5, paddingRight: onClose ? 28 : 0 }}>
          Complete your profile to get personalized study plans, skill tracking, and tailored mentoring advice.
        </p>
        <button className="btn btn-accent" onClick={onStartSetup} type="button" style={{ width: '100%', height: 40 }}>
          Complete Setup
        </button>
      </div>
    </div>
  );
}
