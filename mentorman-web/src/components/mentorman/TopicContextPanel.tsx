'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from './icons';
import { truncateFilename } from '@/lib/chat-upload/utils';
import {
  deleteTopicDocument,
  listTopicDocuments,
  uploadTopicDocuments,
  type TopicDocument,
} from '@/lib/topic-documents-api';

const SUPPORTED_ACCEPT = '.pdf,.csv';

/**
 * Right-side panel holding this topic's persistent context documents —
 * separate from the composer's one-off "paste into this message" attach
 * flow. Files uploaded here are embedded (metadata.topic_id) and injected
 * into every turn for this topic, not just the turn they were sent on.
 */
export function TopicContextPanel({ topicId }: { topicId: string | null }) {
  const [documents, setDocuments] = useState<TopicDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
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
      <div className="context-panel-head">
        <span className="context-panel-title">Context</span>
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
          title="Collapse context"
          aria-label="Collapse context"
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

      {error && <div className="context-panel-error">{error}</div>}

      {documents.length === 0 ? (
        <div className="context-panel-empty">
          No documents yet. Add notes, syllabi, or problem sets for the mentor to reference in this topic.
        </div>
      ) : (
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
    </div>
  );
}
