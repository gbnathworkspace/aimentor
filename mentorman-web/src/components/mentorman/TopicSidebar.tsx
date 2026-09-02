'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../auth/useAuth';
import { Icon } from './icons';
import { relativeTime } from '../../lib/topics/relativeTime';
import type { TopicListItem } from '../../lib/topics/types';
import type { CoreProfile } from '@/lib/mentorman-api';
import { DeleteTopicDialog } from './DeleteTopicDialog';

export interface TopicSidebarProps {
  selectedTopicId?: string;
  onSelectTopic: (topicId: string) => void;
  onNewTopic: () => void;
  onViewArchived?: () => void;
  onClearActiveTopic?: () => void;
  refreshKey?: number; // increment to trigger re-fetch
  view?: string;
  onNav?: (v: string) => void;
  profile?: CoreProfile | null;
  avatarUrl?: string | null;
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

const UNGROUPED = '__ungrouped__';
type TopicGroup = { key: string; label: string; subject: string | null; items: TopicListItem[] };

/**
 * Bucket topics by their user-assigned subject. Non-empty subjects become
 * groups ordered by their most-recent activity; topics with no subject collect
 * into a trailing "Ungrouped" bucket. Input is already lastActiveAt-desc, so
 * within-group order is preserved.
 */
function groupTopics(topics: TopicListItem[]): TopicGroup[] {
  const map = new Map<string, TopicListItem[]>();
  const ungrouped: TopicListItem[] = [];
  for (const t of topics) {
    const s = (t.subject || '').trim();
    if (!s) { ungrouped.push(t); continue; }
    if (!map.has(s)) map.set(s, []);
    map.get(s)!.push(t);
  }
  const latest = (items: TopicListItem[]) =>
    Math.max(...items.map(i => new Date(i.lastActiveAt).getTime()));
  const groups: TopicGroup[] = [...map.entries()]
    .map(([subject, items]) => ({ key: subject, label: subject, subject, items }))
    .sort((a, b) => latest(b.items) - latest(a.items));
  // Always render the Ungrouped bucket once any subject exists, even empty —
  // it's the drop target that lets a topic be dragged back out of a group.
  if (ungrouped.length || groups.length) {
    groups.push({ key: UNGROUPED, label: 'Ungrouped', subject: null, items: ungrouped });
  }
  return groups;
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
  onClearActiveTopic,
  refreshKey,
  view,
  onNav,
  profile,
  avatarUrl,
  userName,
  isAdmin,
  collapsed,
  onToggleCollapse,
}: TopicSidebarProps) {
  const { logout } = useAuth();
  const [topics, setTopics] = useState<TopicListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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

  // Collapsed group state, persisted so folds survive reload.
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem('mm-collapsed-subjects') || '[]')); }
    catch { return new Set(); }
  });
  useEffect(() => {
    try { localStorage.setItem('mm-collapsed-subjects', JSON.stringify([...collapsedGroups])); } catch {}
  }, [collapsedGroups]);
  const toggleCollapse = (key: string) => setCollapsedGroups((s) => {
    const n = new Set(s);
    n.has(key) ? n.delete(key) : n.add(key);
    return n;
  });

  // Inline subject editor — one row at a time.
  const [editingId, setEditingId] = useState<string | null>(null);
  const skipBlur = useRef(false);
  /** Dragged topic awaiting a name for the group it forms with the drop target. */
  const [pairedId, setPairedId] = useState<string | null>(null);
  const [subjectError, setSubjectError] = useState<string | null>(null);
  const saveSubject = async (topicIds: string | string[], value: string) => {
    setEditingId(null);
    setPairedId(null);
    const ids = Array.isArray(topicIds) ? topicIds : [topicIds];
    const results = await Promise.all(ids.map((id) =>
      fetch(`/api/topic/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: value.trim() }),
      }).then((r) => r.ok).catch(() => false)
    ));
    // A silent failure here looks identical to "grouping is broken" — say so.
    setSubjectError(results.every(Boolean) ? null : "Couldn't save the subject.");
    fetchTopics();
  };

  // Drag a topic onto a subject header to regroup it; onto the ungrouped
  // block to clear its subject. ponytail: native HTML5 DnD, no library.
  const [dragOverKey, setDragOverKey] = useState<string | null>(null);
  const dropTarget = (key: string, subject: string | null) => ({
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setDragOverKey(key); },
    onDragLeave: (e: React.DragEvent) => {
      if (e.currentTarget.contains(e.relatedTarget as Node)) return; // moved onto a child
      setDragOverKey((k) => (k === key ? null : k));
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setDragOverKey(null);
      const id = e.dataTransfer.getData('text/plain');
      const topic = topics.find((t) => t.topicId === id);
      if (!topic) return;
      if ((topic.subject || '').trim() === (subject || '')) return; // already there
      saveSubject(id, subject || '');
    },
  });

  const handleDeleteConfirm = async () => {
    if (!pendingDeleteId || deletingId) return;
    const topicId = pendingDeleteId;
    setDeletingId(topicId);
    setDeleteError(null);
    try {
      const r = await fetch(`/api/topic/${topicId}`, { method: 'DELETE' });
      if (r.status === 404) {
        setPendingDeleteId(null);
        fetchTopics();
        return;
      }
      if (!r.ok) throw new Error('Delete failed');
      setTopics((prev) => prev.filter((t) => t.topicId !== topicId));
      setPendingDeleteId(null);
      if (selectedTopicId === topicId) onClearActiveTopic?.();
    } catch {
      setDeleteError('Could not delete topic. Please try again.');
    } finally {
      setDeletingId(null);
    }
  };

  const groups = groupTopics(topics);
  const hasSubjects = groups.some((g) => g.subject !== null);
  const allSubjects = [...new Set(topics.map((t) => (t.subject || '').trim()).filter(Boolean))];

  /** The subject field — inline on a row, or as the header of a pending group. */
  const subjectInput = (topic: TopicListItem, className: string) => (
    <input
      className={className}
      list="mm-subjects"
      autoFocus
      defaultValue={topic.subject || ''}
      placeholder={pairedId ? 'Name this group…' : 'Subject…'}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); }
        else if (e.key === 'Escape') { skipBlur.current = true; setEditingId(null); setPairedId(null); }
      }}
      onBlur={(e) => {
        if (skipBlur.current) { skipBlur.current = false; return; }
        const value = e.target.value;
        // Empty name on a fresh pair = cancel, don't blank both topics.
        if (pairedId && !value.trim()) { setEditingId(null); setPairedId(null); return; }
        saveSubject(pairedId ? [topic.topicId, pairedId] : topic.topicId, value);
      }}
    />
  );

  const renderRow = (topic: TopicListItem, inPendingGroup = false) => {
    const isActive = selectedTopicId === topic.topicId;
    const isEditing = editingId === topic.topicId;
    // While naming a new group, its two members render inside that group only.
    if (!inPendingGroup && pairedId === topic.topicId) return null;
    if (!inPendingGroup && isEditing && pairedId) {
      const paired = topics.find((t) => t.topicId === pairedId);
      return (
        <div key={topic.topicId} className="sb-group pending-group">
          <div className="sb-group-head">
            <Icon name="chevronDown" size={11} />
            {subjectInput(topic, 'group-name-input')}
          </div>
          {renderRow(topic, true)}
          {paired && renderRow(paired, true)}
        </div>
      );
    }
    return (
      <div
        key={topic.topicId}
        className={`session ${isActive ? 'active' : ''} ${dragOverKey === topic.topicId ? 'drop-over' : ''}`}
        draggable={!isEditing}
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', topic.topicId);
          e.dataTransfer.effectAllowed = 'move';
        }}
        // Dropping onto a row wins over its group/ungrouped container.
        onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setDragOverKey(topic.topicId); }}
        onDragLeave={(e) => {
          if (e.currentTarget.contains(e.relatedTarget as Node)) return;
          setDragOverKey((k) => (k === topic.topicId ? null : k));
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setDragOverKey(null);
          const draggedId = e.dataTransfer.getData('text/plain');
          if (!draggedId || draggedId === topic.topicId) return;
          const subject = (topic.subject || '').trim();
          if (subject) { saveSubject(draggedId, subject); return; }
          const draggedTopic = topics.find((t) => t.topicId === draggedId);
          if ((draggedTopic?.subject || '').trim()) {
            // Dragged topic already belongs to a group — dropping it onto an
            // ungrouped row clears its subject instead of forming a new pair.
            saveSubject(draggedId, '');
            return;
          }
          // Neither is grouped yet — name the subject the pair will form.
          setPairedId(draggedId);
          setEditingId(topic.topicId);
        }}
        onClick={() => onSelectTopic(topic.topicId)}
      >
        <div className="s-row1">
          <span className="s-title">{truncate(topic.title, 60)}</span>
          <span className="s-date">{relativeTime(topic.lastActiveAt)}</span>
        </div>
        {isEditing && !pairedId ? (
          subjectInput(topic, 'subject-input')
        ) : inPendingGroup ? null : (
          <button
            className="session-tag-btn"
            title="Set subject"
            onClick={(e) => { e.stopPropagation(); setEditingId(topic.topicId); }}
          >
            <Icon name="edit" size={12} />
          </button>
        )}
        {!collapsed && !inPendingGroup && (
          <button
            className="session-delete-btn"
            title="Delete topic"
            aria-label={`Delete topic ${topic.title}`}
            onClick={(e) => {
              e.stopPropagation();
              setDeleteError(null);
              setPendingDeleteId(topic.topicId);
            }}
            disabled={deletingId === topic.topicId}
          >
            <Icon name="trash" size={12} />
          </button>
        )}
      </div>
    );
  };

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
        <div style={{ display: 'flex', gap: 4 }}>
          {onNav && !collapsed && isAdmin && (
            <button className={`icon-btn ${view === 'admin' ? 'on' : ''}`} title="Manage users" aria-label="Manage users" onClick={() => onNav('admin')}>
              <Icon name="users" />
            </button>
          )}
          {onNav && !collapsed && isAdmin && (
            <button className={`icon-btn ${view === 'analytics' ? 'on' : ''}`} title="LLM traces" aria-label="LLM traces" onClick={() => onNav('analytics')}>
              <Icon name="chart" />
            </button>
          )}
          {onNav && !collapsed && (
            <button
              className={`icon-btn ${view === 'settings' ? 'on' : ''}`}
              title={(profile?.pending_changes?.length ?? 0) > 0 ? 'Settings — updates suggested' : 'Settings'}
              aria-label={(profile?.pending_changes?.length ?? 0) > 0 ? 'Settings — updates suggested' : 'Settings'}
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
            <button className="icon-btn" title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={onToggleCollapse}>
              <Icon name={collapsed ? 'arrowR' : 'back'} size={14} />
            </button>
          )}
        </div>
      </div>

      {/* New Topic button */}
      <div className="sb-actions">
        <button className="new-session" title="New Topic" aria-label="New Topic" onClick={onNewTopic} style={{ position: 'relative' }}>
          <Icon name="plus" size={15} /> <span className="label">New Topic</span>
          {collapsed && topics.length > 0 && (
            <span className="new-session-count" title={`${topics.length} topics`}>{topics.length}</span>
          )}
        </button>
        {onNav && !collapsed && (
          <button className={`sb-nav-icon ${view === 'dashboard' ? 'on' : ''}`} title="Skill graph" onClick={() => onNav('dashboard')}>
            <Icon name="chart" size={17} />
          </button>
        )}
      </div>

      {/* Section label — also doubles as the "drop here to ungroup" target,
          since the trailing Ungrouped bucket can be scrolled out of view. */}
      <div
        className={`sb-section ${dragOverKey === 'header-home' ? 'drop-over' : ''}`}
        {...dropTarget('header-home', null)}
      >
        <span>Topics</span>
        <span className="count">{loading ? '…' : topics.length}</span>
      </div>

      {subjectError && (
        <div style={{ padding: '4px 12px', fontSize: 11, color: 'var(--danger)' }}>
          {subjectError}
        </div>
      )}

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
        ) : !hasSubjects ? (
          // No subjects assigned yet — keep the plain flat list.
          groups[0].items.map((t) => renderRow(t))
        ) : (
          groups.map((g) => {
            // The trailing Ungrouped bucket isn't a real group — it renders as
            // plain rows at the bottom, with nothing to fold or label.
            if (g.subject === null) {
              return (
                <div
                  key={g.key}
                  className={`sb-ungrouped ${dragOverKey === g.key ? 'drop-over' : ''}`}
                  {...dropTarget(g.key, null)}
                >
                  {g.items.map((t) => renderRow(t))}
                </div>
              );
            }
            const isCollapsed = collapsedGroups.has(g.key);
            return (
              <div
                key={g.key}
                className={`sb-group ${dragOverKey === g.key ? 'drop-over' : ''}`}
                {...dropTarget(g.key, g.subject)}
              >
                <div
                  className="sb-group-head"
                  role="button"
                  tabIndex={0}
                  aria-expanded={!isCollapsed}
                  onClick={() => toggleCollapse(g.key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleCollapse(g.key); }
                  }}
                >
                  <Icon
                    name="chevronDown"
                    size={11}
                    style={{ transform: isCollapsed ? 'rotate(-90deg)' : 'none', transition: 'transform .15s' }}
                  />
                  <span className="sb-group-name">{g.label}</span>
                  <span className="count">{g.items.length}</span>
                </div>
                {!isCollapsed && g.items.map((t) => renderRow(t))}
              </div>
            );
          })
        )}
      </div>

      <datalist id="mm-subjects">
        {allSubjects.map((s) => <option key={s} value={s} />)}
      </datalist>

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
            {avatarUrl ? (
              <img src={avatarUrl} alt="" style={{ width: 30, height: 30, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }} />
            ) : (
              <div className="avatar">{(profile?.name || userName || 'Y')[0].toUpperCase()}</div>
            )}
            <div className="who-wrap" style={{ minWidth: 0 }}>
              <div className="who">{profile?.name || userName || 'You'}</div>
            </div>
          </button>
          <button className="icon-btn" title="Sign out" aria-label="Sign out" onClick={() => logout()} style={{ flexShrink: 0 }}>
            <Icon name="logout" />
          </button>
        </div>
      )}

      {pendingDeleteId && (
        <DeleteTopicDialog
          open={!!pendingDeleteId}
          topicTitle={topics.find((t) => t.topicId === pendingDeleteId)?.title ?? ''}
          onConfirm={handleDeleteConfirm}
          onCancel={() => { setPendingDeleteId(null); setDeleteError(null); }}
          loading={deletingId === pendingDeleteId}
          error={deleteError}
        />
      )}
    </div>
  );
}
