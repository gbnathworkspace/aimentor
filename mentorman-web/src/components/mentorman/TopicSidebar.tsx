'use client';

import React from 'react';
import { useAuth } from '../../auth/useAuth';
import { Icon } from './icons';
import type { CoreProfile } from '@/lib/mentorman-api';

export interface TopicSidebarProps {
  onAskMentor?: () => void;
  onViewArchived?: () => void;
  view?: string;
  onNav?: (v: string) => void;
  profile?: CoreProfile | null;
  avatarUrl?: string | null;
  userName?: string;
  isAdmin?: boolean;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function TopicSidebar({
  onAskMentor,
  onViewArchived,
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

      {onAskMentor && (
        <div className="sb-actions">
          <button className="new-session" title="Ask Mentor" aria-label="Ask Mentor" onClick={onAskMentor}>
            <Icon name="spark" size={15} /> <span className="label">Ask Mentor</span>
          </button>
        </div>
      )}

      {/* Feature nav — each entry opens its own page in the main area. */}
      {onNav && (
        <nav className="sb-nav">
          <button className={`sb-nav-item ${view === 'topics' ? 'on' : ''}`} title="Topics" onClick={() => onNav('topics')}>
            <Icon name="doc" size={15} /> <span className="label">Topics</span>
          </button>
          <button className={`sb-nav-item ${view === 'dashboard' ? 'on' : ''}`} title="Skill graph" onClick={() => onNav('dashboard')}>
            <Icon name="chart" size={15} /> <span className="label">Skill graph</span>
          </button>
          {onViewArchived && (
            <button className="sb-nav-item" title="Archived" onClick={onViewArchived}>
              <Icon name="clock" size={15} /> <span className="label">Archived</span>
            </button>
          )}
        </nav>
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
    </div>
  );
}
