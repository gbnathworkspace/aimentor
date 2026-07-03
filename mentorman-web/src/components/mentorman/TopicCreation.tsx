'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Icon } from './icons';

// ─── Title Validation ─────────────────────────────────────────────────────────

/**
 * Validates a topic title: 1–100 characters after trim, non-empty.
 * Returns an error message string or null if valid.
 * Requirements: 1.4, 1.5
 */
function validateTitle(raw: string): string | null {
  const trimmed = raw.trim();
  if (trimmed.length === 0) return 'Title must not be empty';
  if (trimmed.length > 100) return 'Title must be at most 100 characters';
  return null;
}

// ─── TopicCreation Props ──────────────────────────────────────────────────────

export interface TopicCreationProps {
  onTopicCreated: (topicId: string) => void;
  onCancel: () => void;
  /** When true, skips the title dialog and creates a topic from the first message content. */
  autoCreate?: boolean;
}

// ─── TopicCreation Component ──────────────────────────────────────────────────

/**
 * Handles creating a new topic via an inline form.
 *
 * - Shows a title input with submit/cancel buttons
 * - Validates title (1-100 chars after trim)
 * - Calls POST /api/topics on submit
 * - Supports auto-creation from first message (autoCreate prop)
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
 */
export function TopicCreation({ onTopicCreated, onCancel, autoCreate }: TopicCreationProps) {
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!autoCreate) {
      inputRef.current?.focus();
    }
  }, [autoCreate]);

  const submit = useCallback(async (titleValue: string) => {
    const trimmed = titleValue.trim();
    const validationError = validateTitle(trimmed);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch('/api/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: trimmed }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail || 'Failed to create topic — please try again.');
        return;
      }
      const topic = await res.json();
      const topicId = topic.topicId || topic.topic_id || topic.id;
      onTopicCreated(topicId);
    } catch {
      setError('Connection error — please try again.');
    } finally {
      setSubmitting(false);
    }
  }, [onTopicCreated]);

  /**
   * Auto-create a topic from the first message content.
   * Used by the chat panel when user sends a message without an active topic.
   * The first 100 characters (trimmed) of the message become the title.
   * Requirement: 1.1
   */
  const autoCreateFromMessage = useCallback(async (messageContent: string) => {
    const derived = messageContent.trim().slice(0, 100);
    await submit(derived);
  }, [submit]);

  // Expose autoCreateFromMessage for parent components to call imperatively
  // via ref if needed; for now the autoCreate flow is handled via the prop.
  // If autoCreate is true, this component renders nothing visible — the parent
  // calls autoCreateFromMessage directly or uses the exported utility.

  if (autoCreate) {
    // In auto-create mode, this component doesn't render a form.
    // The parent should call the autoCreateTopic utility directly.
    return null;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(title);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onCancel();
    }
  };

  return (
    <form className="topic-creation" onSubmit={handleSubmit} onKeyDown={handleKeyDown}>
      <div className="topic-creation-header">
        <span className="topic-creation-label">New Topic</span>
        <button
          type="button"
          className="icon-btn"
          title="Cancel"
          onClick={onCancel}
          style={{ padding: 2 }}
        >
          <Icon name="x" size={14} />
        </button>
      </div>
      <div className="topic-creation-field">
        <input
          ref={inputRef}
          className="num-input"
          type="text"
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            if (error) setError(null);
          }}
          placeholder="e.g. Graphs — BFS/DFS"
          maxLength={100}
          disabled={submitting}
          aria-label="Topic title"
          aria-invalid={!!error}
          aria-describedby={error ? 'topic-title-error' : undefined}
          style={{ width: '100%' }}
        />
        {error && (
          <div
            id="topic-title-error"
            className="topic-creation-error"
            role="alert"
          >
            {error}
          </div>
        )}
      </div>
      <div className="topic-creation-actions">
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-sm btn-primary"
          disabled={submitting || !title.trim()}
        >
          {submitting ? 'Creating…' : 'Create'}
        </button>
      </div>
    </form>
  );
}

// ─── TopicRename Props ────────────────────────────────────────────────────────

export interface TopicRenameProps {
  topicId: string;
  currentTitle: string;
  onRenamed: (newTitle: string) => void;
}

// ─── TopicRenameInput Component ───────────────────────────────────────────────

/**
 * Inline editable title for renaming an existing topic.
 *
 * - Click the title to enter edit mode
 * - Validates title (1-100 chars after trim)
 * - Calls PATCH /api/topic/{id} on submit
 * - Shows validation error inline
 *
 * Requirements: 1.2, 1.4, 1.5
 */
export function TopicRenameInput({ topicId, currentTitle, onRenamed }: TopicRenameProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(currentTitle);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  // Sync value if currentTitle changes externally
  useEffect(() => {
    if (!editing) {
      setValue(currentTitle);
    }
  }, [currentTitle, editing]);

  const startEdit = () => {
    setValue(currentTitle);
    setError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setValue(currentTitle);
    setError(null);
    setEditing(false);
  };

  const save = async () => {
    const trimmed = value.trim();
    const validationError = validateTitle(trimmed);
    if (validationError) {
      setError(validationError);
      return;
    }

    // No change — just close
    if (trimmed === currentTitle.trim()) {
      setEditing(false);
      return;
    }

    setError(null);
    setSaving(true);
    try {
      const res = await fetch(`/api/topic/${topicId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: trimmed }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail || 'Failed to rename — please try again.');
        return;
      }
      onRenamed(trimmed);
      setEditing(false);
    } catch {
      setError('Connection error — please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      save();
    } else if (e.key === 'Escape') {
      cancelEdit();
    }
  };

  if (!editing) {
    return (
      <button
        className="topic-rename-trigger"
        onClick={startEdit}
        title="Click to rename"
        aria-label={`Rename topic: ${currentTitle}`}
      >
        <span className="topic-rename-title">{currentTitle}</span>
        <svg viewBox="0 0 16 16" width={12} height={12} fill="none"
             stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M11.5 2.5l2 2L5 13H3v-2z" />
          <path d="M9.5 4.5l2 2" />
        </svg>
      </button>
    );
  }

  return (
    <div className="topic-rename-form">
      <div className="topic-rename-row">
        <input
          ref={inputRef}
          className="num-input"
          type="text"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            // Auto-save on blur if value changed, otherwise cancel
            if (value.trim() && value.trim() !== currentTitle.trim()) {
              save();
            } else {
              cancelEdit();
            }
          }}
          maxLength={100}
          disabled={saving}
          aria-label="Topic title"
          aria-invalid={!!error}
          aria-describedby={error ? `topic-rename-error-${topicId}` : undefined}
          style={{ flex: 1 }}
        />
        <button
          className="btn btn-sm btn-ghost"
          onClick={cancelEdit}
          disabled={saving}
          type="button"
        >
          Cancel
        </button>
        <button
          className="btn btn-sm btn-primary"
          onClick={save}
          disabled={saving || !value.trim()}
          type="button"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
      {error && (
        <div
          id={`topic-rename-error-${topicId}`}
          className="topic-creation-error"
          role="alert"
        >
          {error}
        </div>
      )}
    </div>
  );
}

// ─── Utility: Auto-create topic from message ──────────────────────────────────

/**
 * Creates a topic using the first 100 characters of the message as title.
 * Returns the new topicId or null on failure.
 *
 * Meant to be called by the chat panel when a user sends the first message
 * without having an active topic selected.
 *
 * Requirement: 1.1
 */
export async function autoCreateTopic(messageContent: string): Promise<string | null> {
  const title = messageContent.trim().slice(0, 100);
  if (!title) return null;

  try {
    const res = await fetch('/api/topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) return null;
    const topic = await res.json();
    return topic.topicId || topic.topic_id || topic.id || null;
  } catch {
    return null;
  }
}
