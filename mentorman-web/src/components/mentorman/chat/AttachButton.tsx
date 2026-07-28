'use client';

import React, { useRef } from 'react';
import { Icon } from '../icons';

const SUPPORTED_ACCEPT = '.pdf,.docx,.csv,.xlsx,.json,.txt,.md,.rtf';

export interface AttachButtonProps {
  disabled?: boolean;
  onSelect: (fileList: FileList | null) => void;
}

/**
 * AttachButton — the toolbar trigger for staging documents. Deliberately a
 * plain "+" (not an upload-arrow) so it doesn't read as a second Send button
 * next to the composer's actual Send arrow.
 */
export function AttachButton({ disabled, onSelect }: AttachButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={SUPPORTED_ACCEPT}
        multiple
        style={{ display: 'none' }}
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => {
          // Copy out via onSelect (which converts to an array immediately)
          // before resetting .value — Chrome's FileList is live-bound to the
          // input, so clearing .value first would empty this same reference.
          onSelect(e.target.files);
          if (inputRef.current) inputRef.current.value = '';
        }}
      />
      <button
        type="button"
        className="tool-btn"
        title="Attach documents"
        aria-label="Attach documents"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
      >
        <Icon name="plus" size={15} />
      </button>
    </>
  );
}
