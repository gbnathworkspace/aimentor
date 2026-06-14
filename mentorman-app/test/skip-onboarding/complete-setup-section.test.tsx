import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { CompleteSetupSection } from '@/app/components/mentorman/CompleteSetupSection';

describe('CompleteSetupSection', () => {
  it('renders a "Complete Setup" button', () => {
    render(<CompleteSetupSection onStartSetup={() => {}} />);
    const button = screen.getByRole('button', { name: 'Complete Setup' });
    expect(button).toBeInTheDocument();
  });

  it('renders a heading indicating profile completion', () => {
    render(<CompleteSetupSection onStartSetup={() => {}} />);
    expect(screen.getByText('Complete Your Profile')).toBeInTheDocument();
  });

  it('renders a description explaining the value of completing setup', () => {
    render(<CompleteSetupSection onStartSetup={() => {}} />);
    expect(
      screen.getByText(/personalized study plans, skill tracking/i)
    ).toBeInTheDocument();
  });

  it('calls onStartSetup when the button is clicked', async () => {
    const onStartSetup = vi.fn();
    render(<CompleteSetupSection onStartSetup={onStartSetup} />);
    const button = screen.getByRole('button', { name: 'Complete Setup' });
    await userEvent.click(button);
    expect(onStartSetup).toHaveBeenCalledTimes(1);
  });

  it('calls onStartSetup when activated via keyboard', async () => {
    const onStartSetup = vi.fn();
    render(<CompleteSetupSection onStartSetup={onStartSetup} />);
    const button = screen.getByRole('button', { name: 'Complete Setup' });
    button.focus();
    await userEvent.keyboard('{Enter}');
    expect(onStartSetup).toHaveBeenCalledTimes(1);
  });

  it('uses the settings section layout (set-section class)', () => {
    render(<CompleteSetupSection onStartSetup={() => {}} />);
    const section = screen.getByTestId('complete-setup-section');
    expect(section).toHaveClass('set-section');
  });

  it('uses the accent button style for visual prominence', () => {
    render(<CompleteSetupSection onStartSetup={() => {}} />);
    const button = screen.getByRole('button', { name: 'Complete Setup' });
    expect(button.className).toContain('btn-accent');
  });
});
