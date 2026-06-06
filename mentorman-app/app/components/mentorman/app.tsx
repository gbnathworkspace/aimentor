'use client';

import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import { Sidebar } from './ui';
import { ChatPanel } from './chat';
import { Dashboard } from './dashboard';
import { Onboarding, EvalPanel, SessionEnd, Settings, MobileChat } from './screens';
import { TweaksPanel, TweakSection, TweakRadio, TweakColor, useTweaks } from './tweaks';
import { ACCENTS, catToMode, type ModeId, type ToneId, type Topic } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';

type View = 'chat' | 'dashboard' | 'evaluation' | 'summary' | 'settings' | 'onboarding';

const LAUNCH_ITEMS: { id: string; num: string; label: string }[] = [
  { id: 'onboarding', num: '01', label: 'Onboarding' },
  { id: 'chat',       num: '02', label: 'Mentor chat' },
  { id: 'dashboard',  num: '03', label: 'Skill graph' },
  { id: 'evaluation', num: '04', label: 'Evaluation' },
  { id: 'summary',    num: '05', label: 'Session end' },
  { id: 'settings',   num: '06', label: 'Settings' },
  { id: 'mobile',     num: '07', label: 'Mobile chat' },
];

function Launcher({ view, mobileOpen, onGo }: {
  view: string;
  mobileOpen: boolean;
  onGo: (target: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const active = mobileOpen ? 'mobile' : view;
  return (
    <div className="launcher">
      {open && (
        <div className="launcher-menu" onMouseLeave={() => setOpen(false)}>
          <div className="lm-label">Jump to screen</div>
          {LAUNCH_ITEMS.map(it => (
            <div key={it.id} className={`lm-item ${active === it.id ? 'active' : ''}`}
                 onClick={() => { onGo(it.id); setOpen(false); }}>
              <span className="lm-num">{it.num}</span>
              <span>{it.label}</span>
              <span className="lm-dot" />
            </div>
          ))}
        </div>
      )}
      <button className="launcher-btn" onClick={() => setOpen(o => !o)}>
        <span className="led" /> screens <Icon name="dots" size={14} />
      </button>
    </div>
  );
}

export function MentorManApp() {
  const [t, setTweak] = useTweaks({ accent: '#34d399', tone: 'balanced', density: 'cozy' });
  const [view, setView] = useState<View>('chat');
  const [activeSession, setActiveSession] = useState('s1');
  const [mode, setMode] = useState<ModeId>('topic');
  const [mobileOpen, setMobileOpen] = useState(false);
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
    if (cat === 'Eval') { setView('evaluation'); }
    else { setMode(catToMode[cat] || 'topic'); setView('chat'); }
  };

  const startTopic = () => {
    localStorage.removeItem('mentorman_draft');
    setActiveSession('new');
    setActiveSessionTitle(null);
    setMode('topic');
    setView('chat');
  };

  const go = (target: string) => {
    if (target === 'mobile') { setMobileOpen(true); return; }
    setMobileOpen(false);
    if (target === 'chat') { setActiveSession('s1'); setMode('topic'); }
    if (target === 'evaluation') { setActiveSession('s7'); }
    setView(target as View);
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
            onNav={(v) => { setMobileOpen(false); setView(v as View); }}
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
          {view === 'evaluation' && (
            <EvalPanel onComplete={() => { setActiveSession('new'); setMode('topic'); setView('chat'); }} />
          )}
          {view === 'summary' && (
            <SessionEnd
              onFollow={() => { setActiveSession('new'); setMode('topic'); setView('chat'); }}
              onBack={() => { setActiveSession('s1'); setView('chat'); }}
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

      {mobileOpen && <MobileChat onClose={() => setMobileOpen(false)} tone={t.tone as ToneId} />}

      <Launcher view={view} mobileOpen={mobileOpen} onGo={go} />

      <TweaksPanel title="Tweaks">
        <TweakSection label="Accent" />
        <TweakColor label="Accent color" value={t.accent}
          options={['#34d399', '#5b9bff', '#a78bfa', '#fbbf24', '#fb7185']}
          onChange={v => setTweak('accent', v)} />
        <TweakSection label="Mentor" />
        <TweakRadio label="Tone" value={t.tone}
          options={['tough', 'balanced', 'encouraging']}
          onChange={v => setTweak('tone', v)} />
        <TweakSection label="Layout" />
        <TweakRadio label="Density" value={t.density}
          options={['compact', 'cozy', 'comfy']}
          onChange={v => setTweak('density', v)} />
      </TweaksPanel>
    </div>
  );
}
