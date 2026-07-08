'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import { TopicSidebar } from './TopicSidebar';
import { ArchivedTopics } from './ArchivedTopics';
import { ChatPanel } from './chat';
import { Dashboard } from './dashboard';
import { Onboarding, Settings, AdminUsers } from './screens';
import { DEFAULT_TONE, type ModeId, type ToneId, type Topic } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';

type View = 'chat' | 'dashboard' | 'settings' | 'admin' | 'onboarding' | 'deferred-onboarding';

export function MentorManApp() {
  // Baked-in defaults (the demo tweaks panel was removed for production).
  const t = { density: 'cozy' };
  const [view, setView] = useState<View>('chat');
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const [mode, setMode] = useState<ModeId>('topic');
  const [tone, setTone] = useState<ToneId>(DEFAULT_TONE);
  const [profile, setProfile] = useState<CoreProfile | null>(null);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [userName, setUserName] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicsVersion, setTopicsVersion] = useState(0);
  const [chatKey, setChatKey] = useState(0);
  const [sidebarView, setSidebarView] = useState<'topics' | 'archived'>('topics');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Fetch user name via /api/me
  useEffect(() => {
    fetch('/api/me')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.name) setUserName(data.name);
        setIsAdmin(!!data?.is_admin);
      })
      .catch(() => {});
  }, []);

  // Fetch profile — auto-route to onboarding if none exists
  useEffect(() => {
    fetch('/api/profile')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setProfile(data);
        } else {
          setView('onboarding');
        }
        setProfileLoaded(true);
      })
      .catch(() => { setProfileLoaded(true); });
  }, []);

  // Fetch skills for alert derivation in ChatPanel
  useEffect(() => {
    fetch('/api/skills')
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setTopics(data); })
      .catch(() => {});
  }, []);

  // clear one-shot entrance animations once finished
  useEffect(() => {
    const onEnd = (e: AnimationEvent) => {
      const el = e.target as HTMLElement;
      if (el && el.style && el.classList && !el.classList.contains('keep-anim')) {
        el.style.animation = 'none';
      }
    };
    document.addEventListener('animationend', onEnd, true);
    return () => document.removeEventListener('animationend', onEnd, true);
  }, []);

  const refreshProfile = () => {
    fetch('/api/profile')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setProfile(data); })
      .catch(() => {});
  };

  const startTopic = (_t?: Topic) => {
    setActiveTopic(null);
    setMode('topic');
    setView('chat');
    setChatKey(k => k + 1);
  };

  const fullScreen = view === 'onboarding' || view === 'deferred-onboarding';

  const sidebarContent = sidebarView === 'archived' ? (
    <ArchivedTopics
      onSelectTopic={(topicId) => { setActiveTopic(topicId); setView('chat'); setSidebarView('topics'); }}
      onBack={() => setSidebarView('topics')}
      collapsed={sidebarCollapsed}
      onToggleCollapse={() => setSidebarCollapsed(c => !c)}
    />
  ) : (
    <TopicSidebar
      selectedTopicId={activeTopic ?? undefined}
      onSelectTopic={(topicId) => { setActiveTopic(topicId); setView('chat'); }}
      onNewTopic={() => { setActiveTopic(null); setView('chat'); setChatKey(k => k + 1); }}
      onViewArchived={() => setSidebarView('archived')}
      refreshKey={topicsVersion}
      view={view}
      onNav={(v) => setView(v as View)}
      profile={profile}
      userName={userName}
      isAdmin={isAdmin}
      collapsed={sidebarCollapsed}
      onToggleCollapse={() => setSidebarCollapsed(c => !c)}
    />
  );

  return (
    <div className={`app ${fullScreen ? 'full' : ''} density-${t.density}`}>
      {view === 'deferred-onboarding' ? (
        <Onboarding
          userName={userName}
          deferred
          onFinish={(goal) => {
            refreshProfile();
            if (goal) {
              fetch('/api/topics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: goal.slice(0, 100) }) })
                .then(r => r.json())
                .then(data => {
                  const topicId = data.topicId || data.topic_id || data.id;
                  setActiveTopic(topicId);
                  setView('chat');
                  setTopicsVersion(v => v + 1);
                })
                .catch(() => { setActiveTopic(null); setView('chat'); });
            } else {
              setActiveTopic(null);
              setView('chat');
            }
            setChatKey(k => k + 1);
          }}
          onAbandon={() => setView('settings')}
        />
      ) : fullScreen ? (
        <Onboarding userName={userName} onFinish={(goal) => {
          refreshProfile();
          if (goal) {
            fetch('/api/topics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: goal.slice(0, 100) }) })
              .then(r => r.json())
              .then(data => {
                const topicId = data.topicId || data.topic_id || data.id;
                setActiveTopic(topicId);
                setView('chat');
                setTopicsVersion(v => v + 1);
              })
              .catch(() => { setActiveTopic(null); setView('chat'); });
          } else {
            setActiveTopic(null);
            setView('chat');
          }
        }} />
      ) : !profileLoaded ? (
        <>
          {sidebarContent}
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', border: '3px solid var(--accent)', borderTopColor: 'transparent', animation: 'spin 0.7s linear infinite' }} />
          </div>
        </>
      ) : (
        <>
          {sidebarContent}
          {view === 'chat' && (
            <ChatPanel
              key={chatKey}
              topicId={activeTopic}
              mode={mode}
              setMode={setMode}
              tone={tone}
              setTone={setTone}
              onNav={(v) => setView(v as View)}
              onTopicUpdated={() => setTopicsVersion(v => v + 1)}
              onTopicCreated={(topicId) => { setActiveTopic(topicId); setTopicsVersion(v => v + 1); }}
              topics={topics}
              profile={profile}
              onStartDeferredOnboarding={() => setView('deferred-onboarding')}
            />
          )}
          {view === 'dashboard' && (
            <Dashboard onStartTopic={startTopic} profile={profile} />
          )}
          {view === 'settings' && (
            <Settings
              profile={profile}
              onReset={() => { setProfile(null); setView('onboarding'); }}
              onStartDeferredOnboarding={() => setView('deferred-onboarding')}
              onSaved={refreshProfile}
            />
          )}
          {view === 'admin' && <AdminUsers />}
        </>
      )}
    </div>
  );
}
