'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import { relativeTime } from '../../lib/topics/relativeTime';
import type { TopicListItem } from '../../lib/topics/types';

export interface ArchivedTopicsProps {
  onSelectTopic: (topicId: string) => void;
  onBack: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

/** Truncate text to maxLen characters, appending "..." if truncated. */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

/** Skeleton placeholder for loading state. */
function ArchivedTopicSkeleton() {
  return (
    <div className="session" style={{ pointerEvents: 'none', opacity: 0.45 }}>
      <div className="s-row1">
        <span
          className="s-title"
          style={{
            background: 'var(--card-3)',
            borderRadius: 4,
            color: 'transparent',
            userSelect: 'none',
          }}
        >
          Loading archived topic...
        </span>
      </div>
      <div className="s-row2">
        <span
          style={{
            background: 'var(--card-3)',
            borderRadius: 4,
            color: 'transparent',
            userSelect: 'none',
            fontSize: 11,
            padding: '2px 6px',
          }}
        >
          Preview text placeholder
        </span>
      </div>
    </div>
  );
}

export function ArchivedTopics({ onSelectTopic, onBack, collapsed, onToggleCollapse }: ArchivedTopicsProps) {
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchArchivedTopics = () => {
    setLoading(true);
    setError(false);
    fetch('/api/topics/archived')
      .then((r) => {
        if (!r.ok) throw new Error('Failed to fetch archived topics');
        return r.json();
      })
      .then((data: TopicListItem[]) => {
        if (Array.isArray(data)) {
          setTopics(data);
        } else {
          setTopics([]);
        }
      })
      .catch(() => {
        setError(true);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchArchivedTopics();
  }, []);

  return (
    <div className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Header */}
      <div className="sb-head">
        <div className="brand">
          <img
            src={collapsed ? '/logo-mark.svg' : '/logo-full.svg'}
            alt="MentorMan"
            className="brand-logo"
          />
        </div>
        {onToggleCollapse && (
          <button className="icon-btn" title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={onToggleCollapse}>
            <Icon name={collapsed ? 'arrowR' : 'back'} size={14} />
          </button>
        )}
      </div>

      {/* Back button */}
      <div className="sb-actions">
        <button className="new-session" title="Back to Topics" onClick={onBack}>
          <Icon name="back" size={15} /> <span className="label">Back to Topics</span>
        </button>
      </div>

      {/* Section label */}
      <div className="sb-section">
        <span>Archived Topics</span>
        <span className="count">{loading ? '…' : topics.length}</span>
      </div>

      {/* Archived topic list */}
      <div className="session-list">
        {loading ? (
          <>
            <ArchivedTopicSkeleton />
            <ArchivedTopicSkeleton />
            <ArchivedTopicSkeleton />
          </>
        ) : error ? (
          <div style={{ padding: '20px 12px', textAlign: 'center' }}>
            <div
              style={{
                color: 'var(--muted)',
                fontSize: 12,
                lineHeight: 1.5,
                marginBottom: 12,
              }}
            >
              Unable to load archived topics. Please try again.
            </div>
            <button
              className="btn btn-sm btn-ghost"
              onClick={fetchArchivedTopics}
              style={{ width: '100%' }}
            >
              Retry
            </button>
          </div>
        ) : topics.length === 0 ? (
          <div style={{ padding: '20px 12px', textAlign: 'center' }}>
            <div
              style={{
                color: 'var(--muted)',
                fontSize: 12,
                lineHeight: 1.5,
                marginBottom: 12,
              }}
            >
              No archived topics. Topics you archive will appear here.
            </div>
          </div>
        ) : (
          topics.map((topic) => (
            <div
              key={topic.topicId}
              className="session"
              onClick={() => onSelectTopic(topic.topicId)}
              style={{ cursor: 'pointer' }}
            >
              <div className="s-row1">
                <span className="s-title">{truncate(topic.title, 60)}</span>
                <span className="s-date">
                  {relativeTime(topic.lastActiveAt)}
                </span>
              </div>
              <div className="s-row2">
                <span
                  style={{
                    fontSize: 11,
                    color: 'var(--muted)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '100%',
                  }}
                >
                  {truncate(topic.messagePreview || '', 80)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
