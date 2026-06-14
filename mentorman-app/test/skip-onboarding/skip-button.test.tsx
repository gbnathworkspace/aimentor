import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { SkipButton } from '@/app/components/mentorman/SkipButton';

describe('SkipButton', () => {
  it('renders with label "Skip"', () => {
    render(<SkipButton onSkip={() => {}} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Skip');
  });

  it('has aria-label="Skip" for assistive technologies', () => {
    render(<SkipButton onSkip={() => {}} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    expect(button).toHaveAttribute('aria-label', 'Skip');
  });

  it('is keyboard-focusable', () => {
    render(<SkipButton onSkip={() => {}} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    button.focus();
    expect(button).toHaveFocus();
  });

  it('calls onSkip when clicked', async () => {
    const onSkip = vi.fn();
    render(<SkipButton onSkip={onSkip} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    await userEvent.click(button);
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('calls onSkip when activated via keyboard', async () => {
    const onSkip = vi.fn();
    render(<SkipButton onSkip={onSkip} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    button.focus();
    await userEvent.keyboard('{Enter}');
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('uses ghost/outline button style (visually subordinate)', () => {
    render(<SkipButton onSkip={() => {}} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    expect(button.className).toContain('btn-ghost');
  });

  it('uses btn-sm for font size no larger than primary action elements', () => {
    render(<SkipButton onSkip={() => {}} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    expect(button.className).toContain('btn-sm');
  });

  it('is enabled by default', () => {
    render(<SkipButton onSkip={() => {}} />);
    const button = screen.getByRole('button', { name: 'Skip' });
    expect(button).not.toBeDisabled();
  });

  it('can be disabled via prop', () => {
    const onSkip = vi.fn();
    render(<SkipButton onSkip={onSkip} disabled />);
    const button = screen.getByRole('button', { name: 'Skip' });
    expect(button).toBeDisabled();
  });

  it('does not call onSkip when disabled and clicked', async () => {
    const onSkip = vi.fn();
    render(<SkipButton onSkip={onSkip} disabled />);
    const button = screen.getByRole('button', { name: 'Skip' });
    await userEvent.click(button);
    expect(onSkip).not.toHaveBeenCalled();
  });
});
