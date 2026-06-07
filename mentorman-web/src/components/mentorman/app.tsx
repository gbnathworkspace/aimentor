'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import { Sidebar } from './ui';
import { ChatPanel } from './chat';
import { Dashboard } from './dashboard';
import { Onboarding, SessionEnd, Settings } from './screens';
import { ACCENTS, catToMode, type ModeId, type ToneId, type Topic } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';

type View = 'chat' | 'dashboard' | 'summary' | 'settings' | 'onboarding';

export function MentorManApp() {
  // Baked-in defaults (the demo tweaks panel was removed for production).
  const t = { accent: '#34d399', tone: 'balanced' as ToneId, density: 'cozy' };
  const [view, setView] = useState<View>('chat');
  const [activeSession, setActiveSession] = useState('new');
  const [mode, setMode] = useState<ModeId>('topic');
  const [profile, setProfile] = useState<CoreProfile | null>(null);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [userName, setUserName] = useState('');
  const [topics, setTopics] = useState<Topic[]>([]);
  const [activeSessionTitle, setActiveSessionTitle] = useState<string | null>(null);
  const [sessionsVersion, setSessionsVersion] = useState(0);

  // Fetch user name from Clerk via /api/me
  useEffect(() => {
    fetch('/api/me')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.name) setUserName(data.name); })
      .catch(() => {});
  }, []);

  // Fetch profile — auto-route to onboarding if none exists, resume draft if one exists
  useEffect(() => {
    fetch('/api/profile')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setProfile(data);
          try {
            const raw = localStorage.getItem('mentorman_draft');
            if (raw) {
              const draft = JSON.parse(raw);
              if (draft?.msgs?.length > 0) {
                setActiveSession('new');
                if (draft.title) setActiveSessionTitle(draft.title);
              }
            }
          } catch {}
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

  // apply accent + ink to :root
  useEffect(() => {
    const ink = (ACCENTS[t.accent] || ACCENTS['#34d399']).ink;
    document.documentElement.style.setProperty('--accent', t.accent);
    document.documentElement.style.setProperty('--accent-ink-2', ink);
  }, [t.accent]);

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

  const pickSession = (id: string, type?: string, title?: string) => {
    setActiveSession(id);
    if (title) setActiveSessionTitle(title);
    const cat = type ?? 'Topic';
    setMode(catToMode[cat] || 'topic');
    setView('chat');
  };

  const startTopic = () => {
    localStorage.removeItem('mentorman_draft');
    setActiveSession('new');
    setActiveSessionTitle(null);
    setMode('topic');
    setView('chat');
  };

  // Don't render until we know whether to show onboarding or the app
  if (!profileLoaded) return null;

  const fullScreen = view === 'onboarding';

  return (
    <div className={`app ${fullScreen ? 'full' : ''} density-${t.density}`}>
      {fullScreen ? (
        <Onboarding userName={userName} onFinish={(goal) => {
          localStorage.removeItem('mentorman_draft');
          refreshProfile();
          setActiveSession('new');
          setActiveSessionTitle(goal || null);
          setMode('topic');
          setView('chat');
        }} />
      ) : (
        <>
          <Sidebar
            view={view}
            activeSession={activeSession}
            onPickSession={pickSession}
            onNav={(v) => setView(v as View)}
            onNew={() => { localStorage.removeItem('mentorman_draft'); setActiveSession('new'); setMode('planning'); setView('chat'); }}
            profile={profile}
            userName={userName}
            refreshKey={sessionsVersion}
          />
          {view === 'chat' && (
            <ChatPanel
              sessionId={activeSession}
              sessionTitle={activeSessionTitle ?? undefined}
              mode={mode}
              setMode={setMode}
              tone={t.tone as ToneId}
              onNav={(v) => setView(v as View)}
              onSessionSaved={() => setSessionsVersion(v => v + 1)}
              topics={topics}
            />
          )}
          {view === 'dashboard' && (
            <Dashboard onStartTopic={startTopic} profile={profile} />
          )}
          {view === 'summary' && (
            <SessionEnd
              onFollow={() => { setActiveSession('new'); setMode('topic'); setView('chat'); }}
              onBack={() => { setActiveSession('new'); setView('chat'); }}
            />
          )}
          {view === 'settings' && (
            <Settings
              profile={profile}
              onReset={() => { setProfile(null); setView('onboarding'); }}
              onSaved={refreshProfile}
            />
          )}
        </>
      )}
    </div>
  );
}
