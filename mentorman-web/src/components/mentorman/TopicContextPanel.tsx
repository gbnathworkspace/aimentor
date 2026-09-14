'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from './icons';
import { truncateFilename } from '@/lib/chat-upload/utils';
import { TOOL_LABELS, TOOL_DETAILS, type ToolEvent } from './data';
import {
  deleteTopicDocument,
  listTopicDocuments,
  uploadTopicDocuments,
  type TopicDocument,
} from '@/lib/topic-documents-api';

const SUPPORTED_ACCEPT = '.pdf,.csv';

function formatElapsed(ms: number): string {
  const s = ms / 1000;
  return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`;
}

// Timeline of tool calls made for the most recent reply. Stays visible after
// the reply finishes — the user asked to keep it around as a reference —
// until they dismiss it or send another message (chat.tsx resets it then).
// No error state: the TOOL_MARKER protocol only ever emits "start"/"end", so
// there's nothing to render for it.
function WorkingOnReply({ events, onDismiss }: { events: ToolEvent[]; onDismiss: () => void }) {
  // Re-render every second so a still-running step's "Ns so far" keeps
  // ticking even between stream chunks (network waits between tool calls).
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!events.some(e => e.endedAt === undefined)) return;
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, [events]);

  const [open, setOpen] = useState(true);

  const now = Date.now();
  const runningCount = events.filter(e => e.endedAt === undefined).length;
  const summary = events.length === 0
    ? 'Nothing yet — steps will show up here as the next reply works.'
    : runningCount > 0
    ? `Running ${TOOL_LABELS[events[events.length - 1].name] ?? events[events.length - 1].name}…`
    : `${events.length} step${events.length === 1 ? '' : 's'} so far`;

  return (
    <div className="context-panel-section working-section">
      <div className="context-panel-head">
        <button
          type="button"
          className="icon-btn section-toggle"
          title={open ? 'Collapse' : 'Expand'}
          aria-label={open ? 'Collapse working on this reply' : 'Expand working on this reply'}
          aria-expanded={open}
          onClick={() => setOpen(o => !o)}
        >
          <Icon name="chevronDown" size={14} style={{ transform: open ? undefined : 'rotate(-90deg)' }} />
        </button>
        <span className="context-panel-title">Working on this reply</span>
        {events.length > 0 && (
          <button
            type="button"
            className="icon-btn"
            title="Clear"
            aria-label="Clear working history"
            onClick={onDismiss}
          >
            <Icon name="x" size={12} />
          </button>
        )}
      </div>
      {open && <div className="working-summary" role="status" aria-live="polite" aria-atomic="true">
        {summary}
      </div>}
      {open && <div className="working-timeline">
        {events.map((ev, i) => {
          const running = ev.endedAt === undefined;
          const elapsed = formatElapsed((ev.endedAt ?? now) - ev.startedAt);
          return (
            <div className="working-step" key={`${ev.name}-${ev.startedAt}`}>
              <div className="working-step-rail">
                <span className={`working-dot ${running ? 'running' : 'done'}`} />
                {i < events.length - 1 && <div className="working-step-line" />}
              </div>
              <div className="working-step-card">
                <div className="working-step-body">
                  <div className="working-step-title">{TOOL_LABELS[ev.name] ?? ev.name}</div>
                  <div className="working-step-detail">{TOOL_DETAILS[ev.name] ?? ''}</div>
                </div>
                <span className="working-step-duration">{running ? `${elapsed} so far` : elapsed}</span>
              </div>
            </div>
          );
        })}
      </div>}
    </div>
  );
}

/**
 * Right-side panel holding this topic's persistent context documents —
 * separate from the composer's one-off "paste into this message" attach
 * flow. Files uploaded here are embedded (metadata.topic_id) and injected
 * into every turn for this topic, not just the turn they were sent on.
 */
export function TopicContextPanel({ topicId, toolEvents, onDismissWorking }: { topicId: string | null; toolEvents?: ToolEvent[]; onDismissWorking?: () => void }) {
  const [documents, setDocuments] = useState<TopicDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [contentOpen, setContentOpen] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    if (!topicId) { setDocuments([]); return; }
    listTopicDocuments(topicId).then(setDocuments);
  }, [topicId]);

  useEffect(() => { refresh(); }, [refresh]);

  const onSelect = useCallback((fileList: FileList | null) => {
    if (!topicId || !fileList || fileList.length === 0) return;
    setError(null);
    setLoading(true);
    uploadTopicDocuments(topicId, Array.from(fileList))
      .then(result => {
        if (result.errors.length > 0) setError(result.errors[0].error);
        // Processing runs in the background — give it a moment before
        // the chunk count would actually show up.
        setTimeout(refresh, 1500);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [topicId, refresh]);

  const onRemove = useCallback((filename: string) => {
    if (!topicId) return;
    setDocuments(docs => docs.filter(d => d.filename !== filename));
    deleteTopicDocument(topicId, filename).catch(() => refresh());
  }, [topicId, refresh]);

  if (!topicId) return null;

  if (collapsed) {
    return (
      <div className="context-panel context-panel-collapsed">
        <button
          type="button"
          className="icon-btn"
          title="Expand context"
          aria-label="Expand context"
          onClick={() => setCollapsed(false)}
        >
          <Icon name="back" size={14} style={{ transform: 'rotate(180deg)' }} />
        </button>
      </div>
    );
  }

  return (
    <div className="context-panel">
      <div className="context-panel-section">
        <div className="context-panel-head">
          <button
            type="button"
            className="icon-btn section-toggle"
            title={contentOpen ? 'Collapse section' : 'Expand section'}
            aria-label={contentOpen ? 'Collapse context section' : 'Expand context section'}
            aria-expanded={contentOpen}
            onClick={() => setContentOpen(o => !o)}
          >
            <Icon name="chevronDown" size={14} style={{ transform: contentOpen ? undefined : 'rotate(-90deg)' }} />
          </button>
          <span className="context-panel-title-group">
            <span className="context-panel-title">Context</span>
            {documents.length > 0 && <span className="context-panel-count">{documents.length}</span>}
          </span>
          <button
            type="button"
            className="icon-btn"
            title="Add a document to this topic's context"
            aria-label="Add document"
            disabled={loading}
            onClick={() => inputRef.current?.click()}
          >
            <Icon name="plus" size={14} />
          </button>
          <button
            type="button"
            className="icon-btn"
            title="Collapse context panel"
            aria-label="Collapse context panel"
            onClick={() => setCollapsed(true)}
          >
            <Icon name="back" size={14} />
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={SUPPORTED_ACCEPT}
            multiple
            style={{ display: 'none' }}
            onChange={(e) => { onSelect(e.target.files); if (inputRef.current) inputRef.current.value = ''; }}
          />
        </div>

        {contentOpen && error && <div className="context-panel-error">{error}</div>}

        {contentOpen && documents.length > 0 && (
          <div className="context-panel-list">
            {documents.map(doc => (
              <div key={doc.filename} className="context-doc-card">
                <Icon name="doc" size={14} />
                <span className="context-doc-name" title={doc.filename}>
                  {truncateFilename(doc.filename)}
                </span>
                <button
                  type="button"
                  className="context-doc-remove"
                  title="Remove document"
                  aria-label={`Remove ${doc.filename}`}
                  onClick={() => onRemove(doc.filename)}
                >
                  <Icon name="x" size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {contentOpen && (
          <button type="button" className="context-panel-dropzone" onClick={() => inputRef.current?.click()} disabled={loading}>
            {documents.length === 0
              ? 'No documents yet — add notes, syllabi, or problem sets.'
              : '+ Add a document'}
          </button>
        )}
      </div>

      <WorkingOnReply events={toolEvents ?? []} onDismiss={() => onDismissWorking?.()} />
    </div>
  );
}
