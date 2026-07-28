'use client';

/**
 * useAttachedFiles — owns the "files staged in the composer, not yet sent"
 * state shared by the attach button and the preview cards above the input.
 * Split out of the old ChatDocumentUploader so attach (toolbar) and preview
 * (above the textarea) can render in different places while sharing state.
 */

import { useState, useCallback } from 'react';
import { validateDocumentFiles, type FileValidationResult } from './document-upload-utils';

const MAX_FILES = 5;
const SKIP_REVIEW_STORAGE_KEY = 'chat-document-upload:skip-review';

export interface UseAttachedFilesReturn {
  fileResults: FileValidationResult[];
  warning: string | null;
  skipReview: boolean;
  hasValidFiles: boolean;
  toggleSkipReview: () => void;
  /** Validates and stages a freshly-picked FileList (from the attach input). */
  selectFiles: (fileList: FileList | null) => void;
  removeFile: (index: number) => void;
  clearAll: () => void;
}

export function useAttachedFiles(): UseAttachedFilesReturn {
  const [fileResults, setFileResults] = useState<FileValidationResult[]>([]);
  const [warning, setWarning] = useState<string | null>(null);

  // Skip Review toggle — session-scoped persistence, defaults to false
  // (review enabled) on each new browser session.
  const [skipReview, setSkipReview] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    try {
      return sessionStorage.getItem(SKIP_REVIEW_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const toggleSkipReview = useCallback(() => {
    setSkipReview((prev) => {
      const next = !prev;
      try {
        sessionStorage.setItem(SKIP_REVIEW_STORAGE_KEY, String(next));
      } catch {
        // sessionStorage unavailable (e.g. private mode) — ignore
      }
      return next;
    });
  }, []);

  const selectFiles = useCallback((fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    let files = Array.from(fileList);

    if (files.length > MAX_FILES) {
      files = files.slice(0, MAX_FILES);
      setWarning(`Maximum ${MAX_FILES} files allowed per upload. Only the first ${MAX_FILES} files were kept.`);
    } else {
      setWarning(null);
    }

    setFileResults(validateDocumentFiles(files));
  }, []);

  const removeFile = useCallback((index: number) => {
    setFileResults((prev) => {
      const next = prev.filter((_, i) => i !== index);
      if (next.length === 0) setWarning(null);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setFileResults([]);
    setWarning(null);
  }, []);

  const hasValidFiles = fileResults.some((r) => r.error === null);

  return { fileResults, warning, skipReview, hasValidFiles, toggleSkipReview, selectFiles, removeFile, clearAll };
}
