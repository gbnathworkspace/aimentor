'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import { relativeTime } from '../../lib/topics/relativeTime';
import type { TopicListItem } from '../../lib/topics/types';

export interface TopicSidebarProps {
  selectedTopicId?: string;
  onSelectTopic: (topicId: string) => void;
  onNewTopic: () => void;
  onViewArchived?: () => void;
  refreshKey?: number; // increment to trigger re-fetch
}

/** Truncate text to maxLen characters, appending "..." if truncated. */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

/** Skeleton placeholder for loading state. */
function TopicSkeleton() {
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
          Loading topic title...
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

export function TopicSidebar({
  selectedTopicId,
  onSelectTopic,
  onNewTopic,
  onViewArchived,
  refreshKey,
}: TopicSidebarProps) {
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchTopics = () => {
    setLoading(true);
    setError(false);
    fetch('/api/topics')
      .then((r) => {
        if (!r.ok) throw new Error('Failed to fetch topics');
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
    fetchTopics();
  }, [refreshKey]);

  return (
    <div className="sidebar">
      {/* Header */}
      <div className="sb-head">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div className="brand-name">
            Mentor<span className="dim">Man</span>
          </div>
        </div>
      </div>

      {/* New Topic button */}
      <div className="sb-actions">
        <button className="new-session" onClick={onNewTopic}>
          <Icon name="plus" size={15} /> New Topic
        </button>
      </div>

      {/* Section label */}
      <div className="sb-section">
        <span>Topics</span>
        <span className="count">{loading ? '…' : topics.length}</span>
      </div>

      {/* Topic list */}
      <div className="session-list">
        {loading ? (
          <>
            <TopicSkeleton />
            <TopicSkeleton />
            <TopicSkeleton />
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
              Unable to load topics. Please try again.
            </div>
            <button
              className="btn btn-sm btn-ghost"
              onClick={fetchTopics}
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
              No topics yet. Start a new conversation to begin learning.
            </div>
            <button
              className="btn btn-sm btn-ghost"
              onClick={onNewTopic}
              style={{ width: '100%' }}
            >
              <Icon name="plus" size={13} /> New Topic
            </button>
          </div>
        ) : (
          topics.map((topic) => {
            const isActive = selectedTopicId === topic.topicId;
            return (
              <div
                key={topic.topicId}
                className={`session ${isActive ? 'active' : ''}`}
                onClick={() => onSelectTopic(topic.topicId)}
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
            );
          })
        )}
      </div>

      {/* View Archived link */}
      {onViewArchived && (
        <div style={{ padding: '8px 12px', borderTop: '1px solid var(--card-3)' }}>
          <button
            onClick={onViewArchived}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--muted)',
              fontSize: 11,
              cursor: 'pointer',
              padding: '4px 0',
              width: '100%',
              textAlign: 'center',
            }}
          >
            <Icon name="clock" size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            View Archived
          </button>
        </div>
      )}
    </div>
  );
}
