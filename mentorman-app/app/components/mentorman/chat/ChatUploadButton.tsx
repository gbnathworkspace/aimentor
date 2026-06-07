'use client';

import React, { useRef, useState, useCallback } from 'react';
import { Icon } from '../icons';
import {
  validateUploadFile,
  truncateFilename,
  formatFileSize,
} from '@/lib/chat-upload/utils';

export interface ChatUploadButtonProps {
  sessionId: string;
  disabled: boolean;
  onFileSelected: (file: File) => void;
  onFileRemoved: () => void;
}

/**
 * ChatUploadButton — file attachment button for the chat input bar.
 *
 * Renders a paperclip/upload icon button that opens a native file picker
 * filtered to .pdf and .csv. Validates file type and size client-side,
 * displays a preview chip with the filename and size, and allows removal.
 *
 * Accepts max 1 file per message. Disables while upload is in progress.
 */
export function ChatUploadButton({
  sessionId,
  disabled,
  onFileSelected,
  onFileRemoved,
}: ChatUploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleClick = useCallback(() => {
    if (disabled || selectedFile) return;
    inputRef.current?.click();
  }, [disabled, selectedFile]);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      // Reset input value so the same file can be re-selected after removal
      if (inputRef.current) inputRef.current.value = '';

      if (!file) return;

      const validationError = validateUploadFile({
        name: file.name,
        size: file.size,
      });

      if (validationError) {
        setError(validationError);
        setSelectedFile(null);
        return;
      }

      setError(null);
      setSelectedFile(file);
      onFileSelected(file);
    },
    [onFileSelected]
  );

  const handleRemove = useCallback(() => {
    setSelectedFile(null);
    setError(null);
    onFileRemoved();
  }, [onFileRemoved]);

  return (
    <div className="chat-upload-btn-wrapper">
      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.csv"
        style={{ display: 'none' }}
        onChange={handleFileChange}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Attach button */}
      <button
        type="button"
        className="tool-btn"
        title="Attach file"
        aria-label="Attach file"
        onClick={handleClick}
        disabled={disabled}
        style={disabled ? { opacity: 0.4, cursor: 'not-allowed' } : undefined}
      >
        <Icon name="upload" size={15} />
      </button>

      {/* Inline error message */}
      {error && (
        <span className="chat-upload-error" role="alert">
          {error}
        </span>
      )}

      {/* Preview chip */}
      {selectedFile && !error && (
        <div className="chat-upload-chip">
          <Icon name="doc" size={13} />
          <span className="chat-upload-chip-name">
            {truncateFilename(selectedFile.name)}
          </span>
          <span className="chat-upload-chip-size">
            {formatFileSize(selectedFile.size)}
          </span>
          <button
            type="button"
            className="chat-upload-chip-dismiss"
            onClick={handleRemove}
            title="Remove file"
            aria-label="Remove attached file"
            disabled={disabled}
          >
            <Icon name="x" size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
