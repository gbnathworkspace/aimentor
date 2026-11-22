'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Icon } from './icons';
import { relativeTime } from '../../lib/topics/relativeTime';
import type { TopicListItem } from '../../lib/topics/types';
import { DeleteTopicDialog } from './DeleteTopicDialog';

export interface TopicsPageProps {
  selectedTopicId?: string;
  onSelectTopic: (topicId: string) => void;
  onNewTopic: () => void;
  onClearActiveTopic?: () => void;
  refreshKey?: number; // increment to trigger re-fetch
}

/** Truncate text to maxLen characters, appending "..." if truncated. */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

const ALL = '__all__';
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
  groups.push({ key: UNGROUPED, label: 'Ungrouped', subject: null, items: ungrouped });
  return groups;
}

/**
 * Main-area Topics page: a subject list on the left (doubling as drop targets
 * for regrouping) and the selected subject's topics as a card grid on the right.
 */
export function TopicsPage({
  selectedTopicId,
  onSelectTopic,
  onNewTopic,
  onClearActiveTopic,
  refreshKey,
}: TopicsPageProps) {
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
        setTopics(Array.isArray(data) ? data : []);
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

  // Which subject the right-hand pane shows, persisted across reloads.
  const [selectedSubject, setSelectedSubject] = useState<string>(() => {
    try { return localStorage.getItem('mm-topics-subject') || ALL; } catch { return ALL; }
  });
  useEffect(() => {
    try { localStorage.setItem('mm-topics-subject', selectedSubject); } catch {}
  }, [selectedSubject]);
  const [query, setQuery] = useState('');

  // Inline subject editor — one card at a time.
  const [editingId, setEditingId] = useState<string | null>(null);
  const skipBlur = useRef(false);
  const [subjectError, setSubjectError] = useState<string | null>(null);
  const saveSubject = async (topicId: string, value: string) => {
    setEditingId(null);
    const ok = await fetch(`/api/topic/${topicId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: value.trim() }),
    }).then((r) => r.ok).catch(() => false);
    // A silent failure here looks identical to "grouping is broken" — say so.
    setSubjectError(ok ? null : "Couldn't save the subject.");
    fetchTopics();
  };

  // Drag a card onto a subject in the left pane to regroup it; onto
  // "Ungrouped" to clear its subject. Native HTML5 DnD, no library.
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
  const allSubjects = groups.filter((g) => g.subject !== null).map((g) => g.label);
  // A remembered subject can disappear (renamed, emptied), so fall back to All.
  const current = selectedSubject === ALL || groups.some((g) => g.key === selectedSubject)
    ? selectedSubject : ALL;
  const q = query.trim().toLowerCase();
  const matches = (t: TopicListItem) => !q || t.title.toLowerCase().includes(q);

  const subjectItems = [
    { key: ALL, label: 'All topics', count: topics.length, subject: null as string | null, drop: false },
    ...groups.map((g) => ({ key: g.key, label: g.label, count: g.items.length, subject: g.subject, drop: true })),
  ];
  // "All topics" shows each subject as its own section; any other pick shows one grid.
  const visibleSections = groups
    .filter((g) => current === ALL || g.key === current)
    .map((g) => ({ ...g, items: g.items.filter(matches) }))
    .filter((g) => g.items.length);
  const currentLabel = subjectItems.find((i) => i.key === current)?.label ?? 'All topics';

  /** The subject field shown on a card while its subject is being edited. */
  const subjectInput = (topic: TopicListItem) => (
    <input
      className="subject-input"
      list="mm-subjects"
      autoFocus
      aria-label={`Subject for ${topic.title}`}
      defaultValue={topic.subject || ''}
      placeholder="Subject…"
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); }
        else if (e.key === 'Escape') { skipBlur.current = true; setEditingId(null); }
      }}
      onBlur={(e) => {
        if (skipBlur.current) { skipBlur.current = false; return; }
        saveSubject(topic.topicId, e.target.value);
      }}
    />
  );

  const renderCard = (topic: TopicListItem) => {
    const isActive = selectedTopicId === topic.topicId;
    const isEditing = editingId === topic.topicId;
    return (
      <div
        key={topic.topicId}
        className={`tp-card ${isActive ? 'active' : ''}`}
        draggable={!isEditing}
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', topic.topicId);
          e.dataTransfer.effectAllowed = 'move';
        }}
      >
        <button className="tp-card-main" onClick={() => onSelectTopic(topic.topicId)}>
          <span className="tp-card-title">{truncate(topic.title, 80)}</span>
          <span className="tp-card-date">{relativeTime(topic.lastActiveAt)}</span>
        </button>
        {isEditing && subjectInput(topic)}
        <div className="tp-card-actions">
          <button
            className="tp-card-btn"
            title="Set subject"
            aria-label={`Set subject for ${topic.title}`}
            onClick={() => setEditingId(topic.topicId)}
          >
            <Icon name="edit" size={13} />
          </button>
          <button
            className="tp-card-btn danger"
            title="Delete topic"
            aria-label={`Delete topic ${topic.title}`}
            onClick={() => { setDeleteError(null); setPendingDeleteId(topic.topicId); }}
            disabled={deletingId === topic.topicId}
          >
            <Icon name="trash" size={13} />
          </button>
        </div>
      </div>
    );
  };

  const emptyState = (text: string, action?: React.ReactNode) => (
    <div className="topics-empty">
      <div>{text}</div>
      {action}
    </div>
  );

  return (
    <div className="dash">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">Topics</div>
          <div className="ph-sub">{loading ? 'loading…' : `${topics.length} topics`} · drag a card onto a subject to group it</div>
        </div>
        <div className="ph-right">
          <button className="new-session" style={{ padding: '0 16px' }} onClick={onNewTopic}>
            <Icon name="plus" size={15} /> New Topic
          </button>
        </div>
      </div>

      <div className="topics-layout">
        <nav className="topics-subjects" aria-label="Subjects">
          <div className="topics-eyebrow">Subjects</div>
          {subjectItems.map((item) => (
            <button
              key={item.key}
              className={`topics-subject ${current === item.key ? 'on' : ''} ${dragOverKey === item.key ? 'drop-over' : ''}`}
              aria-current={current === item.key ? 'true' : undefined}
              onClick={() => setSelectedSubject(item.key)}
              {...(item.drop ? dropTarget(item.key, item.subject) : {})}
            >
              <span className="topics-subject-name">{item.label}</span>
              <span className="count">{loading ? '…' : item.count}</span>
            </button>
          ))}
          <div className="topics-subjects-hint">New subject: use the pencil on a card.</div>
        </nav>

        <section className="topics-main" aria-label="Topic list">
          <div className="topics-main-head">
            <h2 className="topics-main-title">{currentLabel}</h2>
            <input
              className="topics-search"
              type="search"
              placeholder="Search topics"
              aria-label="Search topics"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          {subjectError && <div className="topics-error">{subjectError}</div>}

          {loading ? (
            <div className="tp-grid">
              {[0, 1, 2, 3].map((i) => <div key={i} className="tp-card skeleton" />)}
            </div>
          ) : error ? (
            emptyState('Unable to load topics. Please try again.',
              <button className="btn btn-sm btn-ghost" onClick={fetchTopics}>Retry</button>)
          ) : topics.length === 0 ? (
            emptyState('No topics yet. Start a new conversation to begin learning.',
              <button className="btn btn-sm btn-ghost" onClick={onNewTopic}>
                <Icon name="plus" size={13} /> New Topic
              </button>)
          ) : visibleSections.length === 0 ? (
            emptyState(q ? `No topics match "${query.trim()}".` : 'Nothing here yet. Drag a card onto this subject.')
          ) : (
            visibleSections.map((g) => (
              <div key={g.key} className="tp-section">
                {current === ALL && (
                  <div className="topics-eyebrow tp-section-head">
                    <span>{g.label}</span>
                    <span className="count">{g.items.length}</span>
                  </div>
                )}
                <div className="tp-grid">{g.items.map(renderCard)}</div>
              </div>
            ))
          )}
        </section>
      </div>

      <datalist id="mm-subjects">
        {allSubjects.map((s) => <option key={s} value={s} />)}
      </datalist>

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
