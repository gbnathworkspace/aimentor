'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Icon } from './icons';
import { Brand, Bubble, VerdictMsg, Typing, GapBar, fmt } from './ui';
import { SEEDS, EVAL_SEED, EVAL_DONE_EXTRA, MODES, mentorSystemPrompt, type MessageItem, type ToneId } from './data';

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
        setThread(prev => [...prev, { who: 'mentor', text: "That gives us ~18 hrs/week. I've built your plan around it — we adjust as we go.", _id: 'qf' }]);
        const goal = answers.current[0] ?? 'FAANG-level SWE role';
        const availability = answers.current[2] ?? '2 hrs/day';
        fetch('/api/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            goal,
            deadline: 'Aug 2026',
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
            {[0,1,2,3].map(i => (
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
              <h3>You&apos;re all set, Arjun.</h3>
              <div className="setup-lines">
                <div className="setup-line"><span className="k">goal</span><span className="v">20 LPA by Aug 2026</span></div>
                <div className="setup-line"><span className="k">availability</span><span className="v">18 hrs / week</span></div>
                <div className="setup-line"><span className="k">biggest gap</span><span className="v">Graphs (40%) · DP (45%)</span></div>
                <div className="setup-line"><span className="k">indexed</span><span className="v">184 LeetCode problems</span></div>
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
            <div className="meta">today · 11:42 → 12:18 · 36 min · 8 messages</div>
          </div>
          <div className="se-summary">
            <div className="label">Summary</div>
            <div className="body">
              You revisited BFS layer semantics and got crisp on the queue invariant. We worked a grid-shortest-path warmup, then a variant with zero-cost edges where you hit the wall — you correctly spotted that plain BFS breaks but reached for the wrong fix. We named 0-1 BFS as the right tool and queued it for next session. You stayed on topic the whole way.
            </div>
          </div>
          <div className="se-cards">
            <div className="se-card">
              <div className="h">Skill update</div>
              <div className="skill-line">graphs <span className="arrow">·</span> medium <span className="arrow">→</span> <span className="new">medium+</span></div>
              <div style={{ marginTop: 4 }}>
                <GapBar cur={58} req={85} animate />
                <div className="gapbar-labels" style={{ marginTop: 5, marginBottom: 0 }}>
                  <span>was 45%</span><span className="arrow">+13 this session</span><span>req 85%</span>
                </div>
              </div>
            </div>
            <div className="se-card">
              <div className="h">Weak areas to revisit</div>
              <div className="area-tags" style={{ marginTop: 2 }}>
                <span className="area-tag warn">0-1 BFS</span>
                <span className="area-tag warn">negative cycles</span>
                <span className="area-tag warn">Dijkstra heap</span>
              </div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)', marginTop: 'auto' }}>3 topics flagged</div>
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
export function Settings({ onReset }: { onReset: () => void }) {
  const [editAvail, setEditAvail] = useState(false);
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="ph-left"><div className="ph-title">Settings</div><div className="ph-sub">goal · availability · data</div></div>
      </div>
      <div className="set-body">
        <div className="set-inner">
          <div className="set-section">
            <div className="set-label">Goal</div>
            <div className="set-row"><div className="k">Goal</div><div className="v">20 LPA SWE role</div><button className="btn btn-sm btn-ghost">Edit</button></div>
            <div className="set-row"><div className="k">Target date</div><div className="v">Aug 2026</div><button className="btn btn-sm btn-ghost">Edit</button></div>
          </div>

          <div className="set-section">
            <div className="set-label">Availability</div>
            <div className="avail-card">
              <div className="avail-top">
                <div className="main">18 <span className="unit">hrs / week</span></div>
                <span className="avail-breakdown">2 hrs weekdays · 4 hrs weekends</span>
              </div>
              {editAvail && (
                <div className="avail-form">
                  <div className="avail-field"><label>Weekday hrs</label><input className="num-input" type="number" defaultValue={2} /></div>
                  <div className="avail-field"><label>Weekend hrs</label><input className="num-input" type="number" defaultValue={4} /></div>
                  <div style={{ flex: 1 }} />
                  <button className="btn btn-sm btn-ghost" onClick={() => setEditAvail(false)}>Cancel</button>
                  <button className="btn btn-sm btn-primary" onClick={() => setEditAvail(false)}>Save</button>
                </div>
              )}
              {!editAvail && <button className="btn btn-sm btn-ghost" style={{ alignSelf: 'flex-start' }} onClick={() => setEditAvail(true)}>Adjust hours</button>}
            </div>
          </div>

          <div className="set-section">
            <div className="set-label">Data sources</div>
            <div className="data-row">
              <div className="file-ico">PDF</div>
              <div className="info"><div className="fname">resume.pdf <span className="ok">active</span></div><div className="fmeta">uploaded May 2026 · goal calibration</div></div>
              <button className="btn btn-sm btn-ghost">Re-upload</button>
            </div>
            <div className="data-row">
              <div className="file-ico">CSV</div>
              <div className="info"><div className="fname">leetcode_export.csv <span className="ok">active</span></div><div className="fmeta">uploaded May 2026 · 184 problems indexed</div></div>
              <button className="btn btn-sm btn-ghost">Re-upload</button>
            </div>
          </div>

          <div className="set-section">
            <div className="set-label danger">Danger zone</div>
            <div className="danger-card">
              <button className="danger-btn" onClick={onReset}>Reset goal and skill graph</button>
              <div className="danger-note">This clears your skill graph and restarts onboarding.</div>
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
