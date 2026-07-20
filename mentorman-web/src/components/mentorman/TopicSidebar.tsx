'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '../../auth/useAuth';
import { Icon } from './icons';
import { relativeTime } from '../../lib/topics/relativeTime';
import type { TopicListItem } from '../../lib/topics/types';
import type { CoreProfile } from '@/lib/mentorman-api';

export interface TopicSidebarProps {
  selectedTopicId?: string;
  onSelectTopic: (topicId: string) => void;
  onNewTopic: () => void;
  onViewArchived?: () => void;
  refreshKey?: number; // increment to trigger re-fetch
  view?: string;
  onNav?: (v: string) => void;
  profile?: CoreProfile | null;
  userName?: string;
  isAdmin?: boolean;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
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
  view,
  onNav,
  profile,
  userName,
  isAdmin,
  collapsed,
  onToggleCollapse,
}: TopicSidebarProps) {
  const { logout } = useAuth();
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
    <div className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Header */}
      <div className="sb-head">
        <div className="brand">
          <img src="/logo-full.svg" alt="MentorMan" className="brand-logo" />
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {onNav && !collapsed && isAdmin && (
            <button className={`icon-btn ${view === 'admin' ? 'on' : ''}`} title="Manage users" onClick={() => onNav('admin')}>
              <Icon name="users" />
            </button>
          )}
          {onNav && !collapsed && (
            <button
              className={`icon-btn ${view === 'settings' ? 'on' : ''}`}
              title={(profile?.pending_changes?.length ?? 0) > 0 ? 'Settings — updates suggested' : 'Settings'}
              onClick={() => onNav('settings')}
              style={{ position: 'relative' }}
            >
              <Icon name="gear" />
              {(profile?.pending_changes?.length ?? 0) > 0 && (
                <span style={{
                  position: 'absolute', top: 4, right: 4, width: 7, height: 7,
                  borderRadius: '50%', background: 'var(--accent)',
                }} />
              )}
            </button>
          )}
          {onToggleCollapse && (
            <button className="icon-btn" title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={onToggleCollapse}>
              <Icon name={collapsed ? 'arrowR' : 'back'} size={14} />
            </button>
          )}
        </div>
      </div>

      {/* New Topic button */}
      <div className="sb-actions">
        <button className="new-session" title="New Topic" onClick={onNewTopic}>
          <Icon name="plus" size={15} /> <span className="label">New Topic</span>
        </button>
        {onNav && !collapsed && (
          <button className={`sb-nav-icon ${view === 'dashboard' ? 'on' : ''}`} title="Skill graph" onClick={() => onNav('dashboard')}>
            <Icon name="chart" size={17} />
          </button>
        )}
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
        <div className="sb-archived-link" style={{ padding: '8px 12px', borderTop: '1px solid var(--card-3)' }}>
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

      {/* Account footer → Profile / Settings + sign out */}
      {onNav && (
        <div className="sb-foot" style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
          <button
            onClick={() => onNav('settings')}
            title="View profile & settings"
            style={{ cursor: 'pointer', background: 'none', border: 'none', flex: 1, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10, padding: 0, minWidth: 0 }}
          >
            {profile?.avatar ? (
              <img src={profile.avatar} alt="" style={{ width: 30, height: 30, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }} />
            ) : (
              <div className="avatar">{(profile?.name || userName || profile?.email || 'Y')[0].toUpperCase()}</div>
            )}
            <div style={{ minWidth: 0 }}>
              <div className="who">{profile?.name || userName || profile?.email?.split('@')[0] || 'You'}</div>
            </div>
          </button>
          <button className="icon-btn" title="Sign out" onClick={() => logout()} style={{ flexShrink: 0 }}>
            <Icon name="logout" />
          </button>
        </div>
      )}
    </div>
  );
}
