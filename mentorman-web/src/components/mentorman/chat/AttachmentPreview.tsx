'use client';

import React from 'react';
import { Icon } from '../icons';
import { truncateFilename, formatFileSize } from '@/lib/chat-upload/utils';
import type { FileValidationResult } from '@/lib/chat-upload/document-upload-utils';

export interface AttachmentPreviewProps {
  fileResults: FileValidationResult[];
  warning: string | null;
  skipReview: boolean;
  disabled?: boolean;
  onRemove: (index: number) => void;
  onClearAll: () => void;
  onToggleSkipReview: () => void;
}

/**
 * AttachmentPreview — staged-file cards rendered above the text input, inside
 * the same composer box. There is no submit button here: sending is the
 * composer's one Send action, which picks up these files itself.
 */
export function AttachmentPreview({
  fileResults,
  warning,
  skipReview,
  disabled,
  onRemove,
  onClearAll,
  onToggleSkipReview,
}: AttachmentPreviewProps) {
  if (fileResults.length === 0 && !warning) return null;

  return (
    <div className="chat-document-uploader">
      {warning && (
        <span className="chat-upload-warning" role="alert">
          {warning}
        </span>
      )}

      {fileResults.length > 0 && (
        <div className="chat-document-preview-area" role="list" aria-label="Selected files">
          {fileResults.map((result, index) => (
            <div
              key={`${result.file.name}-${index}`}
              className={`chat-document-chip ${result.error ? 'chat-document-chip--error' : ''}`}
              role="listitem"
            >
              <Icon name="doc" size={13} />
              <span className="chat-document-chip-name" title={result.file.name}>
                {truncateFilename(result.file.name)}
              </span>
              <span className="chat-document-chip-size">{formatFileSize(result.file.size)}</span>
              {result.error && (
                <span className="chat-document-chip-error" role="alert">
                  {result.error}
                </span>
              )}
              <button
                type="button"
                className="chat-document-chip-remove"
                onClick={() => onRemove(index)}
                title="Remove file"
                aria-label={`Remove ${result.file.name}`}
                disabled={disabled}
              >
                <Icon name="x" size={12} />
              </button>
            </div>
          ))}

          <div className="chat-document-actions-row">
            <label
              className="chat-document-skip-review"
              title="When enabled, extracted facts are written directly to your profile without review"
            >
              <input
                type="checkbox"
                className="chat-document-skip-review-input"
                checked={skipReview}
                onChange={onToggleSkipReview}
                disabled={disabled}
                aria-label="Skip Review"
              />
              <span className="chat-document-skip-review-track" aria-hidden="true">
                <span className="chat-document-skip-review-thumb" />
              </span>
              <span className="chat-document-skip-review-label">Skip Review</span>
            </label>

            <button
              type="button"
              className="chat-document-clear-all"
              title="Clear all files"
              aria-label="Clear all files"
              onClick={onClearAll}
              disabled={disabled}
            >
              Clear all
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
