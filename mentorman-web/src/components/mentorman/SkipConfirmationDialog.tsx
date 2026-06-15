import React, { useEffect, useRef, useCallback } from 'react';

export interface SkipConfirmationDialogProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  error?: string | null;
}

export function SkipConfirmationDialog({
  open,
  onConfirm,
  onCancel,
  loading = false,
  error = null,
}: SkipConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open && cancelBtnRef.current) {
      cancelBtnRef.current.focus();
    }
  }, [open]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) {
        e.preventDefault();
        onCancel();
        return;
      }
      if (e.key === 'Tab') {
        const dialog = dialogRef.current;
        if (!dialog) return;
        const focusable = dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
    },
    [loading, onCancel]
  );

  if (!open) return null;

  return (
    <div className="skip-dialog-overlay" onClick={!loading ? onCancel : undefined}>
      <div
        ref={dialogRef}
        className="skip-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="skip-dialog-title"
        aria-describedby="skip-dialog-desc"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <h2 id="skip-dialog-title" className="skip-dialog-title">Skip setup?</h2>
        <p id="skip-dialog-desc" className="skip-dialog-desc">
          You can always complete your profile later from Settings. Without a full profile,
          your mentor&apos;s advice will be general rather than personalized.
        </p>
        {error && (
          <div className="skip-dialog-error" role="alert">{error}</div>
        )}
        <div className="skip-dialog-actions">
          <button ref={cancelBtnRef} className="btn btn-ghost" onClick={onCancel} disabled={loading} type="button">
            Go Back
          </button>
          <button className="btn btn-accent" onClick={onConfirm} disabled={loading} type="button" aria-busy={loading}>
            {loading ? 'Skipping…' : 'Skip Setup'}
          </button>
        </div>
      </div>
    </div>
  );
}
