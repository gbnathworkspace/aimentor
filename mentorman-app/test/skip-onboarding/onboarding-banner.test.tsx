import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { OnboardingBanner } from '@/app/components/mentorman/OnboardingBanner';

describe('OnboardingBanner', () => {
  let sessionStorageMock: Record<string, string>;

  beforeEach(() => {
    sessionStorageMock = {};
    vi.stubGlobal('sessionStorage', {
      getItem: vi.fn((key: string) => sessionStorageMock[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key];
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {};
      }),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the banner with the correct message text', () => {
    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(
      screen.getByText('Complete your profile to get personalized study plans and skill tracking.')
    ).toBeInTheDocument();
  });

  it('message text is 120 characters or fewer', () => {
    const message = 'Complete your profile to get personalized study plans and skill tracking.';
    expect(message.length).toBeLessThanOrEqual(120);
  });

  it('renders a "Complete Setup" link/button', () => {
    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(screen.getByRole('button', { name: 'Complete Setup' })).toBeInTheDocument();
  });

  it('calls onComplete when "Complete Setup" is clicked', async () => {
    const onComplete = vi.fn();
    render(<OnboardingBanner onComplete={onComplete} onDismiss={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Complete Setup' }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('renders a dismiss button', () => {
    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(screen.getByRole('button', { name: 'Dismiss banner' })).toBeInTheDocument();
  });

  it('hides the banner when dismiss is clicked', async () => {
    const { container } = render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    const dismissBtn = screen.getByRole('button', { name: 'Dismiss banner' });
    await userEvent.click(dismissBtn);
    // Banner should not be in the DOM anymore
    expect(container.querySelector('.onboarding-banner')).not.toBeInTheDocument();
  });

  it('calls onDismiss callback when dismiss is clicked', async () => {
    const onDismiss = vi.fn();
    render(<OnboardingBanner onComplete={() => {}} onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss banner' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('sets sessionStorage on dismiss', async () => {
    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss banner' }));
    expect(sessionStorage.setItem).toHaveBeenCalledWith('mentorman_banner_dismissed', 'true');
  });

  it('does not render when sessionStorage already has dismissed flag', () => {
    sessionStorageMock['mentorman_banner_dismissed'] = 'true';
    const { container } = render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(container.querySelector('.onboarding-banner')).not.toBeInTheDocument();
  });

  it('renders the banner when sessionStorage throws (graceful handling)', () => {
    // Simulate sessionStorage being unavailable
    vi.stubGlobal('sessionStorage', {
      getItem: vi.fn(() => { throw new Error('SecurityError: access denied'); }),
      setItem: vi.fn(() => { throw new Error('SecurityError: access denied'); }),
      removeItem: vi.fn(),
      clear: vi.fn(),
    });

    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(
      screen.getByText('Complete your profile to get personalized study plans and skill tracking.')
    ).toBeInTheDocument();
  });

  it('dismiss still works when sessionStorage throws on setItem', async () => {
    // Allow getItem to work normally (show banner) but setItem throws
    vi.stubGlobal('sessionStorage', {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => { throw new Error('QuotaExceededError'); }),
      removeItem: vi.fn(),
      clear: vi.fn(),
    });

    const onDismiss = vi.fn();
    const { container } = render(<OnboardingBanner onComplete={() => {}} onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss banner' }));
    // Banner should still hide in memory even if sessionStorage write fails
    expect(container.querySelector('.onboarding-banner')).not.toBeInTheDocument();
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('has role="banner" for accessibility', () => {
    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('has an accessible label for the banner region', () => {
    render(<OnboardingBanner onComplete={() => {}} onDismiss={() => {}} />);
    expect(screen.getByLabelText('Complete onboarding reminder')).toBeInTheDocument();
  });
});
