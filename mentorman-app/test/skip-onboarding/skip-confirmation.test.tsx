import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { SkipConfirmationDialog } from '@/app/components/mentorman/SkipConfirmationDialog';

describe('SkipConfirmationDialog', () => {
  const defaultProps = {
    open: true,
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it('renders nothing when open is false', () => {
    const { container } = render(
      <SkipConfirmationDialog {...defaultProps} open={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a dialog with alertdialog role when open', () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toBeInTheDocument();
  });

  it('has aria-modal="true" for assistive technologies', () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('displays "Skip Setup" confirm button', () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const confirmBtn = screen.getByRole('button', { name: 'Skip Setup' });
    expect(confirmBtn).toBeInTheDocument();
  });

  it('displays "Go Back" cancel button', () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const cancelBtn = screen.getByRole('button', { name: 'Go Back' });
    expect(cancelBtn).toBeInTheDocument();
  });

  it('calls onConfirm when "Skip Setup" button is clicked', async () => {
    const onConfirm = vi.fn();
    render(<SkipConfirmationDialog {...defaultProps} onConfirm={onConfirm} />);
    await userEvent.click(screen.getByRole('button', { name: 'Skip Setup' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when "Go Back" button is clicked', async () => {
    const onCancel = vi.fn();
    render(<SkipConfirmationDialog {...defaultProps} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole('button', { name: 'Go Back' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when overlay backdrop is clicked', async () => {
    const onCancel = vi.fn();
    render(<SkipConfirmationDialog {...defaultProps} onCancel={onCancel} />);
    const overlay = document.querySelector('.skip-dialog-overlay')!;
    await userEvent.click(overlay);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('does NOT call onCancel when clicking inside the dialog content', async () => {
    const onCancel = vi.fn();
    render(<SkipConfirmationDialog {...defaultProps} onCancel={onCancel} />);
    const dialog = screen.getByRole('alertdialog');
    await userEvent.click(dialog);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('calls onCancel when Escape key is pressed', async () => {
    const onCancel = vi.fn();
    render(<SkipConfirmationDialog {...defaultProps} onCancel={onCancel} />);
    await userEvent.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  // Loading state
  it('shows "Skipping…" text when loading is true', () => {
    render(<SkipConfirmationDialog {...defaultProps} loading={true} />);
    expect(screen.getByRole('button', { name: 'Skipping…' })).toBeInTheDocument();
  });

  it('disables both buttons when loading', () => {
    render(<SkipConfirmationDialog {...defaultProps} loading={true} />);
    const buttons = screen.getAllByRole('button');
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  it('sets aria-busy on confirm button when loading', () => {
    render(<SkipConfirmationDialog {...defaultProps} loading={true} />);
    const confirmBtn = screen.getByRole('button', { name: 'Skipping…' });
    expect(confirmBtn).toHaveAttribute('aria-busy', 'true');
  });

  it('does not call onCancel on Escape when loading', async () => {
    const onCancel = vi.fn();
    render(
      <SkipConfirmationDialog {...defaultProps} onCancel={onCancel} loading={true} />
    );
    await userEvent.keyboard('{Escape}');
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('does not dismiss on overlay click when loading', async () => {
    const onCancel = vi.fn();
    render(
      <SkipConfirmationDialog {...defaultProps} onCancel={onCancel} loading={true} />
    );
    const overlay = document.querySelector('.skip-dialog-overlay')!;
    await userEvent.click(overlay);
    expect(onCancel).not.toHaveBeenCalled();
  });

  // Error state
  it('displays error message when error prop is set', () => {
    render(
      <SkipConfirmationDialog {...defaultProps} error="Network error — please try again" />
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Network error — please try again');
  });

  it('does not render error element when error is null', () => {
    render(<SkipConfirmationDialog {...defaultProps} error={null} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  // Error state allows retry via confirm button
  it('confirm button still says "Skip Setup" when there is an error (retry)', () => {
    render(
      <SkipConfirmationDialog {...defaultProps} error="Something went wrong" loading={false} />
    );
    expect(screen.getByRole('button', { name: 'Skip Setup' })).not.toBeDisabled();
  });

  // Focus management
  it('focuses the "Go Back" button on open for keyboard safety', () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    expect(screen.getByRole('button', { name: 'Go Back' })).toHaveFocus();
  });

  // Focus trap: Tab wraps around
  it('traps focus within the dialog on Tab', async () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const goBackBtn = screen.getByRole('button', { name: 'Go Back' });
    const skipBtn = screen.getByRole('button', { name: 'Skip Setup' });

    // Start at Go Back (first focusable), tab forward to Skip Setup
    expect(goBackBtn).toHaveFocus();
    await userEvent.tab();
    expect(skipBtn).toHaveFocus();

    // Tab again should wrap to Go Back
    await userEvent.tab();
    expect(goBackBtn).toHaveFocus();
  });

  it('traps focus within the dialog on Shift+Tab', async () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const goBackBtn = screen.getByRole('button', { name: 'Go Back' });
    const skipBtn = screen.getByRole('button', { name: 'Skip Setup' });

    // Start at Go Back, shift+tab should wrap to last: Skip Setup
    expect(goBackBtn).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(skipBtn).toHaveFocus();
  });

  // Overlay blocks pointer events
  it('renders an overlay that blocks interaction below', () => {
    render(<SkipConfirmationDialog {...defaultProps} />);
    const overlay = document.querySelector('.skip-dialog-overlay');
    expect(overlay).toBeInTheDocument();
  });
});
