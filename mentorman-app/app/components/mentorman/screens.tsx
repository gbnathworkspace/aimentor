'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { SEEDS, EVAL_SEED, EVAL_DONE_EXTRA, MODES, mentorSystemPrompt, type MessageItem, type ToneId } from './data';
import type { CoreProfile } from '@/lib/mentorman-api';

// ---------- Onboarding (full screen, guided) ----------------
const ONB_STEPS = [
  {
    q: "What are you working towards?",
    replies: [
      "Crack a FAANG-level SWE role in 3 months",
      "Switch from backend to ML engineering",
      "Pass my system design interview",
    ],
  },
  {
    q: "When do you need to be ready?",
    replies: ["3 months", "6 months", "August 2026"],
  },
  {
    q: "Got it. Drop your resume and LeetCode export and I'll calibrate from there — or skip it.",
    drop: true,
  },
  {
    q: "How many hours a day can you realistically put in? Be honest, not optimistic.",
    replies: ["~1 hr/day", "2 hrs weekdays, 4 on weekends", "4+ hrs/day"],
  },
];

export function Onboarding({ onFinish }: { onFinish: () => void }) {
  const [step, setStep] = useState(0);
  const [thread, setThread] = useState<MessageItem[]>([{ who: 'mentor', text: ONB_STEPS[0].q, _id: 'q0' }]);
  const [uploaded, setUploaded] = useState(false);
  const [done, setDone] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const answers = useRef<string[]>([]);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread, done]);

  const advance = (answerText: string, nextStep: number) => {
    answers.current[step] = answerText;
    setThread(prev => [...prev, { who: 'user', text: answerText, _id: 'a' + prev.length }]);
    setTimeout(() => {
      if (nextStep < ONB_STEPS.length) {
        setThread(prev => [...prev, { who: 'mentor', text: ONB_STEPS[nextStep].q, _id: 'q' + nextStep }]);
        setStep(nextStep);
      } else {
        const goal = answers.current[0] ?? 'FAANG-level SWE role';
        const deadlineRaw = answers.current[1] ?? '3 months';
        const availability = answers.current[3] ?? '2 hrs/day';

        // Resolve deadline: if it looks like "N months", compute date; otherwise use as-is
        let deadline = deadlineRaw;
        const monthsMatch = deadlineRaw.match(/^(\d+)\s*months?$/i);
        if (monthsMatch) {
          const d = new Date();
          d.setMonth(d.getMonth() + parseInt(monthsMatch[1]));
          deadline = d.toISOString().slice(0, 10);
        } else {
          // Try to parse as a date
          const parsed = new Date(deadlineRaw);
          if (!isNaN(parsed.getTime())) {
            deadline = parsed.toISOString().slice(0, 10);
          }
        }

        setThread(prev => [...prev, { who: 'mentor', text: "That gives me everything I need — I've built your plan. Let's get started.", _id: 'qf' }]);
        fetch('/api/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            goal,
            deadline,
            overall_level: 'beginner',
            daily_availability: availability,
            email: '',
          }),
        }).catch(() => {});
        setTimeout(() => setDone(true), 450);
        setStep(nextStep);
      }
    }, 420);
  };

  const cur = ONB_STEPS[step];
  const lastMsg = thread[thread.length - 1];

  return (
    <div className="onb">
      <div className="onb-top">
        <Brand />
        <div className="onb-progress">
          <span>setup</span>
          <div className="onb-steps">
            {[0,1,2,3,4].map(i => (
              <div key={i} className={`s ${i < step || done ? 'done' : i === step ? 'curr' : ''}`} />
            ))}
          </div>
        </div>
      </div>

      <div className="onb-stage" ref={bodyRef}>
        <div className="onb-thread">
          {thread.map((m, i) => (
            i === 0
              ? <div key={m._id} className="onb-q fade-up">{fmt(m.text)}</div>
              : <Bubble key={m._id} who={m.who as 'mentor' | 'user'} item={m} />
          ))}

          {!done && cur && cur.replies && step < ONB_STEPS.length && lastMsg.who === 'mentor' && (
            <div className="quick-replies">
              {cur.replies.map(r => (
                <button key={r} className="quick-reply" onClick={() => advance(r, step + 1)}>{r}</button>
              ))}
            </div>
          )}

          {!done && cur && cur.drop && !uploaded && lastMsg.who === 'mentor' && (
            <>
              <div className="dropzone" onClick={() => setUploaded(true)}>
                <div className="dz-ico"><Icon name="upload" size={18} /></div>
                <div className="dz-copy">
                  <div className="dz-t">Drop files here or click to upload</div>
                  <div className="dz-s">resume.pdf · leetcode_export.csv · optional</div>
                </div>
              </div>
              <div className="quick-replies">
                <button className="quick-reply" onClick={() => advance("Skipping for now", step + 1)}>Skip this</button>
              </div>
            </>
          )}

          {!done && cur && cur.drop && uploaded && (
            <>
              <div style={{ display: 'flex', gap: 8, alignSelf: 'flex-end' }}>
                <span className="file-chip"><Icon name="doc" size={12} /> resume.pdf <span className="ok"><Icon name="check" size={12} /></span></span>
                <span className="file-chip"><Icon name="doc" size={12} /> leetcode_export.csv <span className="ok"><Icon name="check" size={12} /></span></span>
              </div>
              <div className="quick-replies">
                <button className="quick-reply" onClick={() => advance("Uploaded both — 184 problems", step + 1)}>Continue →</button>
              </div>
            </>
          )}

          {done && (
            <div className="setup-card">
              <div className="badge"><span className="dot" /> Setup complete</div>
              <h3>You&apos;re all set.</h3>
              <div className="setup-lines">
                <div className="setup-line"><span className="k">goal</span><span className="v">{answers.current[0] ?? '—'}</span></div>
                <div className="setup-line"><span className="k">deadline</span><span className="v">{answers.current[1] ?? '—'}</span></div>
                <div className="setup-line"><span className="k">availability</span><span className="v">{answers.current[3] ?? '—'}</span></div>
              </div>
              <button className="btn btn-accent" style={{ width: '100%', height: 42 }} onClick={onFinish}>
                Start your first session <Icon name="arrowR" size={15} />
              </button>
            </div>
          )}
        </div>
      </div>

      {!done && (
        <div className="onb-composer">
          <div className="onb-composer-inner">
            <div className="composer-box">
              <textarea rows={1} placeholder="…or type your own answer" style={{ minHeight: 22 }}
                onKeyDown={e => {
                  const el = e.target as HTMLTextAreaElement;
                  if (e.key === 'Enter' && !e.shiftKey && el.value.trim()) {
                    e.preventDefault();
                    advance(el.value.trim(), step + 1);
                    el.value = '';
                  }
                }} />
              <div className="composer-tools">
                <button className="tool-btn">+</button>
                <div className="spacer" />
                <span className="tag">onboarding</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Evaluation panel --------------------------------
export function EvalPanel({ onComplete }: { onComplete: () => void }) {
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [phase, setPhase] = useState<'mid' | 'done'>('mid');
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMsgs([]); setPhase('mid');
    const timers: ReturnType<typeof setTimeout>[] = [];
    EVAL_SEED.forEach((m, i) => timers.push(setTimeout(() => setMsgs(p => [...p, { ...m, _id: 'e' + i }]), 160 + i * 520)));
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, phase]);

  const finish = () => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    EVAL_DONE_EXTRA.forEach((m, i) => timers.push(setTimeout(() => setMsgs(p => [...p, { ...m, _id: 'ed' + i }]), i * 520)));
    setTimeout(() => setPhase('done'), EVAL_DONE_EXTRA.length * 520 + 200);
  };

  const answered = phase === 'done' ? 5 : 2;
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left">
          <div className="ph-title">Evaluation — Graphs · week 3</div>
          <div className="ph-sub">structured Q → verdict → score</div>
        </div>
        <div className="ph-right">
          <span className="eval-progress">
            Q<span className="qn">{phase === 'done' ? 5 : 2}</span>of 5
            <span className="eval-dots">
              {[0,1,2,3,4].map(i => (
                <span key={i} className={`d ${i < answered ? 'done' : i === answered ? 'curr' : ''}`} />
              ))}
            </span>
          </span>
          <span className="pill ok"><span className="ind" /> {phase === 'done' ? '3 / 5' : '1 / 1'} correct</span>
        </div>
      </div>

      <div className="chat-body" ref={bodyRef}>
        <div className="chat-inner">
          {msgs.map((m, i) =>
            m.who === 'verdict'
              ? <VerdictMsg key={m._id || i} item={m as any} />
              : <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />
          )}
        </div>
      </div>

      {phase === 'mid' ? (
        <div className="composer">
          <div className="eval-flag"><span className="dot" /> Evaluation mode — your answer is graded</div>
          <div className="composer-inner">
            <div className="composer-box">
              <textarea rows={1} placeholder="Type your answer to Q3…" />
              <div className="composer-tools">
                <button className="tool-btn">+</button>
                <button className="tool-btn">{'</>'}</button>
                <div className="spacer" />
                <button className="btn btn-accent btn-sm" onClick={finish}>Submit &amp; finish demo</button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="composer">
          <div className="summary-card">
            <div className="sc-h"><span className="check"><Icon name="check" size={12} /></span> Evaluation complete</div>
            <div className="summary-score"><div className="big">3 / 5</div><div className="lbl">graphs · week 3</div></div>
            <div className="summary-cols">
              <div className="summary-col">
                <div className="colhead">Strong areas</div>
                <div className="area-tags">
                  <span className="area-tag strong">BFS recall</span>
                  <span className="area-tag strong">DFS basics</span>
                  <span className="area-tag strong">0-1 BFS reasoning</span>
                </div>
              </div>
              <div className="summary-col">
                <div className="colhead">Weak areas</div>
                <div className="area-tags">
                  <span className="area-tag warn">portal / cost-0 edges</span>
                  <span className="area-tag warn">Dijkstra heap</span>
                </div>
              </div>
            </div>
            <div className="summary-update">Skill graph updated · <b>graphs → medium+</b> · +13%</div>
            <button className="btn btn-accent" style={{ width: '100%', height: 40 }} onClick={onComplete}>
              Start Topic session on weak areas <Icon name="arrowR" size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Session-end summary -----------------------------
export function SessionEnd({ onFollow, onBack }: { onFollow: () => void; onBack: () => void }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">BFS/DFS revision</div><div className="ph-sub">session ended · saved</div></div>
        <div className="ph-right"><span className="pill ok"><span className="ind" /> session saved</span></div>
      </div>
      <div className="se-body">
        <div className="se-inner">
          <div className="se-top">
            <div className="label">Session summary</div>
            <h2 className="title-lg">BFS/DFS revision</h2>
            <div className="meta">today · 36 min · session ended</div>
          </div>
          <div className="se-summary">
            <div className="label">Summary</div>
            <div className="body">
              Session saved. Your skill graph has been updated based on this conversation.
            </div>
          </div>
          <div className="se-actions">
            <button className="btn btn-accent" style={{ flex: 1, height: 42 }} onClick={onFollow}>Start follow-up session <Icon name="arrowR" size={15} /></button>
            <button className="btn btn-ghost" style={{ height: 42 }} onClick={onBack}>Back to sessions</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Settings ----------------------------------------
export function Settings({ profile, onReset, onSaved }: {
  profile: CoreProfile | null;
  onReset: () => void;
  onSaved: () => void;
}) {
  const [editGoal, setEditGoal] = useState(false);
  const [editDeadline, setEditDeadline] = useState(false);
  const [editAvail, setEditAvail] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const [goalVal, setGoalVal] = useState(profile?.goal ?? '');
  const [deadlineVal, setDeadlineVal] = useState(profile?.deadline ?? '');
  const [availVal, setAvailVal] = useState(profile?.daily_availability ?? '');
  const [saving, setSaving] = useState(false);

  // Sync form values when profile loads / changes
  useEffect(() => {
    setGoalVal(profile?.goal ?? '');
    setDeadlineVal(profile?.deadline ?? '');
    setAvailVal(profile?.daily_availability ?? '');
  }, [profile]);

  const save = async (field: Record<string, string>) => {
    setSaving(true);
    try {
      await fetch('/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(field),
      });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    try {
      await fetch('/api/profile', { method: 'DELETE' });
    } finally {
      setSaving(false);
    }
    onReset();
  };

  const deadlineDisplay = profile?.deadline
    ? new Date(profile.deadline).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
    : '—';

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">Profile &amp; Settings</div><div className="ph-sub">goal · availability · data</div></div>
      </div>
      <div className="set-body">
        <div className="set-inner">

          <div className="set-section">
            <div className="set-label">Goal</div>

            <div className="set-row">
              <div className="k">Goal</div>
              {editGoal ? (
                <div style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    className="num-input" style={{ flex: 1 }}
                    value={goalVal}
                    onChange={e => setGoalVal(e.target.value)}
                  />
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditGoal(false); setGoalVal(profile?.goal ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { await save({ goal: goalVal }); setEditGoal(false); }}>Save</button>
                </div>
              ) : (
                <>
                  <div className="v">{profile?.goal ?? '—'}</div>
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditGoal(true)}>Edit</button>
                </>
              )}
            </div>

            <div className="set-row">
              <div className="k">Target date</div>
              {editDeadline ? (
                <div style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    className="num-input" type="date" style={{ flex: 1 }}
                    value={deadlineVal}
                    onChange={e => setDeadlineVal(e.target.value)}
                  />
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditDeadline(false); setDeadlineVal(profile?.deadline ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { await save({ deadline: deadlineVal }); setEditDeadline(false); }}>Save</button>
                </div>
              ) : (
                <>
                  <div className="v">{deadlineDisplay}</div>
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditDeadline(true)}>Edit</button>
                </>
              )}
            </div>
          </div>

          <div className="set-section">
            <div className="set-label">Availability</div>
            <div className="avail-card">
              <div className="avail-top">
                <div className="main">{profile?.daily_availability ?? '—'}</div>
              </div>
              {editAvail ? (
                <div className="avail-form">
                  <div className="avail-field" style={{ flex: 1 }}>
                    <label>Daily availability</label>
                    <input
                      className="num-input" style={{ width: '100%' }}
                      value={availVal}
                      placeholder="e.g. 2 hrs weekdays, 4 on weekends"
                      onChange={e => setAvailVal(e.target.value)}
                    />
                  </div>
                  <button className="btn btn-sm btn-ghost" onClick={() => { setEditAvail(false); setAvailVal(profile?.daily_availability ?? ''); }}>Cancel</button>
                  <button className="btn btn-sm btn-primary" disabled={saving} onClick={async () => { await save({ daily_availability: availVal }); setEditAvail(false); }}>Save</button>
                </div>
              ) : (
                <button className="btn btn-sm btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setEditAvail(true)}>Edit</button>
              )}
            </div>
          </div>

          <div className="set-section">
            <div className="set-label">Data sources</div>
            <div style={{ color: 'var(--muted)', fontSize: 12, padding: '8px 0' }}>
              File ingestion is not yet active. Resume and LeetCode uploads coming soon.
            </div>
          </div>

          <div className="set-section">
            <div className="set-label danger">Danger zone</div>
            <div className="danger-card">
              {confirmReset ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>This will delete your profile and restart onboarding. Are you sure?</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="danger-btn" disabled={saving} onClick={handleReset}>Yes, reset everything</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <button className="danger-btn" onClick={() => setConfirmReset(true)}>Reset goal and skill graph</button>
                  <div className="danger-note">This clears your profile and restarts onboarding.</div>
                </>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

// ---------- Mobile chat (phone frame) -----------------------
export function MobileChat({ onClose, tone }: { onClose: () => void; tone: ToneId }) {
  const [msgs, setMsgs] = useState<MessageItem[]>([]);
  const [val, setVal] = useState('');
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const seed = SEEDS.s1.slice(0, 3);
    const timers: ReturnType<typeof setTimeout>[] = [];
    seed.forEach((m, i) => timers.push(setTimeout(() => setMsgs(p => [...p, { ...m, _id: 'p' + i }]), 200 + i * 520)));
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  const send = async () => {
    const t = val.trim();
    if (!t || busy) return;
    setVal('');
    const um: MessageItem = { who: 'user', text: t, _id: 'u' + Date.now() };
    setMsgs(p => [...p, um]);
    setBusy(true);
    try {
      const history = [...msgs, um].map(m => ({ role: m.who === 'mentor' ? 'assistant' : 'user', content: m.text }));
      const res = await fetch('/api/mentor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system: mentorSystemPrompt('topic', tone, 'Graphs — BFS/DFS warmups'), messages: history }),
      });
      const { text: reply } = await res.json();
      setMsgs(p => [...p, { who: 'mentor', text: (reply || '').trim() || "Say more — where exactly does it break?", _id: 'm' + Date.now() }]);
    } catch {
      setMsgs(p => [...p, { who: 'mentor', text: "Lost my notes for a sec — try again?", _id: 'm' + Date.now() }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mobile-overlay" onClick={onClose}>
      <div className="phone" onClick={e => e.stopPropagation()}>
        <div className="notch" />
        <div className="phone-status"><span>9:41</span><span>MentorMan</span><span>▮▮▮ 100%</span></div>
        <div className="phone-head">
          <div className="back" onClick={onClose}><Icon name="back" /></div>
          <div><div className="pt">Graphs — BFS/DFS</div><div className="ps">● topic mode · active</div></div>
        </div>
        <div className="phone-body" ref={bodyRef}>
          {msgs.map((m, i) => <Bubble key={m._id || i} who={m.who as 'mentor' | 'user'} item={m} />)}
          {busy && <Typing />}
        </div>
        <div className="phone-modes">
          {MODES.map(m => <div key={m.id} className={`phone-mode ${m.id === 'topic' ? 'active' : ''}`}>{m.label}</div>)}
        </div>
        <div className="phone-composer">
          <input className="pc-input" value={val} placeholder="Reply…" onChange={e => setVal(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter') send(); }} />
          <button className="send-btn" onClick={send} disabled={busy || !val.trim()}><Icon name="send" /></button>
        </div>
        <button className="icon-btn phone-close" style={{ background: 'var(--card)', border: '1px solid var(--border)' }} onClick={onClose}><Icon name="x" /></button>
      </div>
    </div>
  );
}
