import { useEffect } from 'react';
import { Link } from 'react-router-dom';

const TITLE = 'MentorMan — The AI mentor that remembers you';
const DESCRIPTION =
  "MentorMan turns your goal, your gaps, and every session into a personal interview-prep roadmap. Socratic teaching, targeted drills, and a mentor that never forgets where you left off.";

const FONTS_HREF =
  'https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap';

/** Sets document title + meta description while this page is mounted, restores previous values on unmount. */
function useDocumentHead(title: string, description: string) {
  useEffect(() => {
    const prevTitle = document.title;
    document.title = title;

    let meta = document.querySelector('meta[name="description"]');
    const wasCreated = !meta;
    const prevContent = meta?.getAttribute('content') ?? null;
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute('name', 'description');
      document.head.appendChild(meta);
    }
    meta.setAttribute('content', description);

    return () => {
      document.title = prevTitle;
      if (wasCreated) {
        meta?.remove();
      } else if (prevContent !== null) {
        meta?.setAttribute('content', prevContent);
      }
    };
  }, [title, description]);
}

/** Loads the landing page's own display/body/mono fonts while mounted; removes the link on unmount. */
function useGoogleFonts(href: string) {
  useEffect(() => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
    return () => { link.remove(); };
  }, [href]);
}

const PAINS = [
  { h: 'No real plan', p: '"I solved 300 problems… randomly. Am I even ready?"' },
  { h: 'Same mistakes, again', p: '"I keep missing the same edge cases in every mock."' },
  { h: 'Tools that forget you', p: '"Every chat starts from zero. I re-explain myself every time."' },
  { h: 'System design guesswork', p: '"I can code, but designing a system in 45 min? No idea."' },
];

const AGENTS = [
  { role: 'Profiler', h: 'Knows you', desc: 'Builds your profile from your resume, target companies, and practice history — your goal, timeline, and current level, always up to date.', chip: 'goal: Senior SWE · Aug 2026' },
  { role: 'Planner', h: 'Charts the path', desc: 'Turns your goal into a week-by-week roadmap, re-prioritized after every session based on what is actually improving.', chip: 'this week: Graphs → BFS' },
  { role: 'Teacher', h: 'Teaches by asking', desc: 'Explains with questions, analogies, and visuals — guiding you to the insight instead of dumping the answer on you.', chip: '"What if the window shrinks?"' },
  { role: 'Quizzer', h: 'Drills your gaps', desc: 'Generates problems and MCQs aimed right at your weak spots, with instant feedback and spaced follow-ups.', chip: 'drill: DP on strings · 5 Qs' },
  { role: 'Reviewer', h: 'Tracks your mistakes', desc: 'Logs every slip — off-by-one, missed edge case, wrong structure — and resurfaces it before it costs you an interview.', chip: 'recurring: empty-input check ×3' },
];

const LAYERS = [
  { tag: 'LAYER 1 — CORE PROFILE', h: 'Your goal, always in view', p: 'Your target role, companies, timeline, and constraints anchor every conversation. Nothing you learn is off-path.', example: 'target: Senior SWE, product cos\ntimeline: Aug 2026' },
  { tag: 'LAYER 2 — SKILL GRAPH', h: 'A live map of your skills', p: 'Every topic — arrays to system design — scored and connected. Your mentor always knows what to teach next.', example: 'sliding_window: 92% ✓\ndynamic_programming: 41% ⚠' },
  { tag: 'LAYER 3 — EPISODIC MEMORY', h: 'Every session, remembered', p: 'Past explanations, questions you asked, mistakes you made — recalled when relevant, so lessons build on each other.', example: 'recall: "we compared this to the\ndelivery-batching example"' },
];

const STEPS = [
  { num: '01', h: 'Share your goal', p: 'Upload your resume, pick your target role and companies, and set your timeline. That is your Core Profile.' },
  { num: '02', h: 'Get your roadmap', p: 'The Planner builds a week-by-week plan from your skill graph — focused on your real gaps, not a generic syllabus.' },
  { num: '03', h: 'Learn by thinking', p: 'Socratic lessons per topic, in persistent threads. Come back tomorrow and continue mid-thought — no recap needed.' },
  { num: '04', h: 'Drill, review, repeat', p: 'Targeted quizzes find the gaps, the mistake tracker keeps you honest, and your skill graph updates every session.' },
];

const COMPARE_OLD = [
  'Random problem grinding with no direction',
  'Chatbots that forget you between sessions',
  'Re-reading answers instead of thinking',
  'Mistakes repeated until interview day',
  'No idea if you are actually ready',
];

const COMPARE_NEW = [
  'A roadmap built from your goal and gaps',
  'A mentor that remembers every session',
  'Socratic teaching that makes ideas stick',
  'A mistake tracker that closes weak spots',
  'A live skill graph showing where you stand',
];

export function LandingPage() {
  useDocumentHead(TITLE, DESCRIPTION);
  useGoogleFonts(FONTS_HREF);

  return (
    <div className="mm-landing">
      <style>{`
.mm-landing{
  --paper:#FBF8F3;
  --paper-2:#F3ECE1;
  --ink:#241C16;
  --ink-body:#2A2016;
  --ink-soft:#6B5D4F;
  --muted:#8A7B6B;
  --line:#EAE0D2;
  --amber:#FBBF24;
  --accent:#C2610C;
  --mastered:#0E8C7F;
  --improving:#D98A15;
  --focus:#C24A32;
  --dark-bg:#241C16;
  --dark-text:#F0E9DF;
  --dark-soft:#B9AC9C;
  --dark-accent:#E8B84B;
  --radius:14px;
  --maxw:1160px;
  --lp-display:'Bricolage Grotesque',sans-serif;
  --lp-body:'IBM Plex Sans',sans-serif;
  --lp-mono:'IBM Plex Mono',monospace;
}
.mm-landing *{margin:0;padding:0;box-sizing:border-box}
.mm-landing{
  font-family:var(--lp-body);
  color:var(--ink-body);
  background:var(--paper);
  line-height:1.6;
  -webkit-font-smoothing:antialiased;
  position:relative;
  scroll-behavior:smooth;
}
.mm-landing ::selection{background:rgba(251,191,36,.30)}
.mm-landing img,.mm-landing svg{display:block;max-width:100%}
.mm-landing a{color:inherit;text-decoration:none}
.mm-landing .wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
.mm-landing .bg-grid{
  position:absolute;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(122,92,52,.07) 1px, transparent 1px),linear-gradient(90deg, rgba(122,92,52,.07) 1px, transparent 1px);
  background-size:34px 34px;
}
.mm-landing .page{position:relative;z-index:1}
.mm-landing h2{font-family:var(--lp-display);font-weight:700;font-size:clamp(28px,4vw,42px);letter-spacing:-.015em;margin-top:14px}
.mm-landing .eyebrow{font-family:var(--lp-mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.mm-landing .section-sub{color:var(--ink-soft);max-width:580px;margin-top:14px;font-size:17px}
@keyframes mm-pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes mm-dash{to{stroke-dashoffset:-40}}
@media (prefers-reduced-motion:reduce){
  .mm-landing *,.mm-landing *::before,.mm-landing *::after{animation:none!important;transition:none!important}
}

/* ---------- Nav ---------- */
.mm-landing .nav{position:sticky;top:0;z-index:50;background:rgba(251,248,243,.82);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.mm-landing .nav-inner{height:70px;display:flex;align-items:center;justify-content:space-between}
.mm-landing .logo{display:flex;align-items:center}
.mm-landing .logo-mark{height:34px;width:auto}
.mm-landing .nav-links{display:flex;gap:30px;font-size:15px;font-weight:500;color:var(--ink-soft)}
.mm-landing .nav-links a:hover{color:var(--ink)}
.mm-landing .nav-cta{display:flex;gap:12px;align-items:center}
.mm-landing .btn{
  display:inline-flex;align-items:center;gap:8px;
  font-family:var(--lp-body);font-weight:600;font-size:15px;
  padding:10px 18px;border-radius:10px;border:1px solid transparent;
  cursor:pointer;transition:filter .15s ease, border-color .15s ease, transform .15s ease;
}
.mm-landing .btn-ghost{border-color:var(--line);background:#fff;color:var(--ink)}
.mm-landing .btn-ghost:hover{border-color:var(--accent)}
.mm-landing .btn-primary{background:var(--amber);color:var(--ink-body);box-shadow:0 4px 14px rgba(212,160,23,.28)}
.mm-landing .btn-primary:hover{filter:brightness(.93)}
.mm-landing .btn-lg{padding:14px 26px;font-size:16px;border-radius:11px}
.mm-landing .btn .arrow{transition:transform .15s ease}
.mm-landing .btn:hover .arrow{transform:translateX(3px)}

/* ---------- Hero ---------- */
.mm-landing .hero{padding:80px 24px 76px;position:relative}
.mm-landing .hero-grid{display:grid;grid-template-columns:1.02fr .98fr;gap:56px;align-items:center}
.mm-landing .badge{
  display:inline-flex;align-items:center;gap:9px;
  font-family:var(--lp-mono);font-size:12px;color:#7A4E12;
  background:#fff;border:1px solid var(--line);border-radius:100px;
  padding:7px 15px;margin-bottom:24px;
}
.mm-landing .badge .dot{width:7px;height:7px;border-radius:50%;background:var(--amber);animation:mm-pulse 2s infinite}
.mm-landing .hero h1{font-family:var(--lp-display);font-weight:800;font-size:clamp(40px,5.4vw,62px);line-height:1.08;letter-spacing:-.02em}
.mm-landing .hero h1 .hl{color:var(--accent)}
.mm-landing .hero .lead{margin-top:22px;font-size:18.5px;color:var(--ink-soft);max-width:520px}
.mm-landing .hero-ctas{display:flex;gap:14px;margin-top:34px;flex-wrap:wrap}
.mm-landing .hero-note{margin-top:16px;font-family:var(--lp-mono);font-size:12.5px;color:var(--muted)}

/* skill graph card */
.mm-landing .graph-card{background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:0 24px 60px rgba(36,28,22,.10);padding:20px}
.mm-landing .card-head{
  display:flex;justify-content:space-between;align-items:center;
  font-family:var(--lp-mono);font-size:12px;color:var(--muted);
  padding-bottom:14px;border-bottom:1px dashed var(--line);
}
.mm-landing .legend{display:flex;gap:18px;font-family:var(--lp-mono);font-size:11.5px;color:var(--muted);padding-top:14px;border-top:1px dashed var(--line);margin-top:8px}
.mm-landing .legend span{display:inline-flex;align-items:center;gap:6px}
.mm-landing .legend i{width:9px;height:9px;border-radius:50%;display:inline-block}
.mm-landing .node text{font-family:var(--lp-mono)}
.mm-landing .edge{stroke:var(--line);stroke-width:1.5}
.mm-landing .edge.lit{stroke:var(--mastered);stroke-dasharray:4 4;animation:mm-dash 3s linear infinite}

/* ---------- Pain ---------- */
.mm-landing .pain{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:92px 24px}
.mm-landing .pain-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:44px}
.mm-landing .pain-card{border:1px solid var(--line);border-radius:var(--radius);padding:26px 22px;background:var(--paper)}
.mm-landing .pain-card .q{font-family:var(--lp-mono);font-size:24px;color:var(--accent);margin-bottom:12px}
.mm-landing .pain-card h3{font-family:var(--lp-display);font-weight:700;font-size:17px;margin-bottom:8px}
.mm-landing .pain-card p{font-size:14.5px;color:var(--ink-soft);font-style:italic}

/* ---------- Agents ---------- */
.mm-landing .agents{padding:96px 24px}
.mm-landing .agent-rows{margin-top:50px;display:flex;flex-direction:column;gap:16px}
.mm-landing .agent{
  display:grid;grid-template-columns:210px 1fr 300px;gap:28px;align-items:center;
  background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:26px 30px;
  transition:box-shadow .15s ease;
}
.mm-landing .agent:hover{box-shadow:0 12px 34px rgba(36,28,22,.08)}
.mm-landing .agent .role{font-family:var(--lp-mono);font-size:12px;color:var(--accent);letter-spacing:.1em;text-transform:uppercase}
.mm-landing .agent h3{font-family:var(--lp-display);font-weight:700;font-size:20px;margin-top:6px}
.mm-landing .agent p{color:var(--ink-soft);font-size:15px}
.mm-landing .agent .chip{justify-self:end;font-family:var(--lp-mono);font-size:12.5px;color:#5A4A38;background:var(--paper-2);border:1px solid var(--line);border-radius:8px;padding:10px 14px}

/* ---------- Memory (dark) ---------- */
.mm-landing .memory{background:var(--dark-bg);color:var(--dark-text);position:relative;overflow:hidden;padding:96px 24px}
.mm-landing .memory .bg-grid{background-image:linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px),linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px)}
.mm-landing .memory-mark{
  position:absolute;top:50%;right:-60px;transform:translateY(-50%) rotate(-4deg);
  width:420px;height:auto;opacity:.14;pointer-events:none;mix-blend-mode:screen;
  -webkit-mask-image:radial-gradient(circle at 50% 42%, #000 34%, transparent 70%);
  mask-image:radial-gradient(circle at 50% 42%, #000 34%, transparent 70%);
}
.mm-landing .memory .eyebrow{color:var(--dark-accent)}
.mm-landing .memory h2{color:#fff}
.mm-landing .memory .section-sub{color:var(--dark-soft)}
.mm-landing .layer-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:52px;position:relative}
.mm-landing .layer-card{border:1px solid rgba(255,255,255,.14);border-radius:var(--radius);padding:28px 24px;background:rgba(255,255,255,.04)}
.mm-landing .layer-card .tag{font-family:var(--lp-mono);font-size:11.5px;color:var(--dark-accent);letter-spacing:.12em}
.mm-landing .layer-card h3{font-family:var(--lp-display);font-weight:700;color:#fff;font-size:19px;margin:10px 0}
.mm-landing .layer-card p{font-size:14.5px;color:var(--dark-soft)}
.mm-landing .layer-card .example{
  margin-top:18px;font-family:var(--lp-mono);font-size:12px;color:#D6CBBB;
  background:rgba(255,255,255,.06);border-left:2px solid var(--amber);
  padding:10px 14px;border-radius:0 8px 8px 0;white-space:pre-line;
}

/* ---------- How it works ---------- */
.mm-landing .how{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:96px 24px}
.mm-landing .step-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:52px}
.mm-landing .step-card{background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:28px 24px}
.mm-landing .step-card .num{font-family:var(--lp-mono);font-size:12px;color:var(--accent);border:1px solid var(--line);border-radius:100px;padding:4px 12px;display:inline-block;margin-bottom:16px}
.mm-landing .step-card h3{font-family:var(--lp-display);font-weight:700;font-size:17.5px;margin-bottom:8px}
.mm-landing .step-card p{font-size:14.5px;color:var(--ink-soft)}

/* ---------- Compare ---------- */
.mm-landing .compare{padding:96px 24px}
.mm-landing .compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:48px}
.mm-landing .compare-col{border-radius:var(--radius);padding:32px}
.mm-landing .compare-col.old{border:1px dashed #D8CBBA;background:var(--paper)}
.mm-landing .compare-col.new{border:1px solid var(--accent);background:linear-gradient(180deg,#FFFDF9,#FBF3E8)}
.mm-landing .compare-col h3{font-family:var(--lp-display);font-weight:700;font-size:19px;margin-bottom:20px}
.mm-landing .compare-col.old h3{color:var(--ink-soft)}
.mm-landing .compare-col ul{list-style:none;display:flex;flex-direction:column;gap:14px}
.mm-landing .compare-col li{display:flex;gap:12px;align-items:flex-start;font-size:15px}
.mm-landing .compare-col.old li{color:var(--ink-soft)}
.mm-landing .compare-col.new li{color:var(--ink)}
.mm-landing .compare-col li .mark{font-family:var(--lp-mono);flex-shrink:0}
.mm-landing .compare-col.old .mark{color:var(--focus)}
.mm-landing .compare-col.new .mark{color:var(--mastered)}

/* ---------- Final CTA ---------- */
.mm-landing .final-cta{padding:110px 24px;text-align:center;border-top:1px solid var(--line)}
.mm-landing .final-cta .inner{max-width:720px;margin:0 auto}
.mm-landing .final-cta h2{font-weight:800;font-size:clamp(30px,4.6vw,48px)}
.mm-landing .final-cta p{margin:16px auto 32px;max-width:520px;color:var(--ink-soft);font-size:17px}

/* ---------- Footer ---------- */
.mm-landing footer{border-top:1px solid var(--line);background:#fff;padding:44px 24px}
.mm-landing .footer-inner{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:20px}
.mm-landing .footer-logo{height:28px;width:auto}
.mm-landing .footer-links{display:flex;gap:24px;font-size:14px;color:var(--ink-soft)}
.mm-landing .footer-links a:hover{color:var(--ink)}
.mm-landing .footer-copy{font-family:var(--lp-mono);font-size:12.5px;color:var(--muted)}
      `}</style>

      <div className="bg-grid" aria-hidden="true" />
      <div className="page">

        {/* NAV */}
        <nav className="nav">
          <div className="wrap nav-inner">
            <a href="#top" className="logo"><img src="/logo-full.svg" alt="MentorMan" className="logo-mark" /></a>
            <div className="nav-links">
              <a href="#agents">Features</a>
              <a href="#memory">Why it works</a>
              <a href="#how">How it works</a>
            </div>
            <div className="nav-cta">
              <Link to="/login" className="btn btn-ghost">Sign in</Link>
              <Link to="/register" className="btn btn-primary">Start free <span className="arrow">→</span></Link>
            </div>
          </div>
        </nav>

        {/* HERO */}
        <header id="top" className="hero">
          <div className="wrap hero-grid">
            <div>
              <span className="badge"><span className="dot"></span> Goal-aware interview prep</span>
              <h1>Interview prep with a mentor that <span className="hl">remembers you</span></h1>
              <p className="lead">MentorMan learns your goal, maps your gaps, and remembers every session — so each lesson, drill, and review picks up right where you left off. You're never starting over.</p>
              <div className="hero-ctas">
                <Link to="/register" className="btn btn-primary btn-lg">Start my prep plan <span className="arrow">→</span></Link>
                <a href="#how" className="btn btn-ghost btn-lg">See how it works</a>
              </div>
              <p className="hero-note">Free to start · No credit card required</p>
            </div>

            <div className="graph-card" aria-label="Example skill graph showing topic mastery">
              <div className="card-head">
                <span>skill-graph · you@mentorman</span>
                <span>updated after last session</span>
              </div>
              <svg viewBox="0 0 460 340" role="img" aria-label="Skill graph with connected topics">
                <line className="edge lit" x1="230" y1="165" x2="110" y2="72" />
                <line className="edge" x1="230" y1="165" x2="350" y2="72" />
                <line className="edge lit" x1="230" y1="165" x2="92" y2="228" />
                <line className="edge" x1="230" y1="165" x2="372" y2="236" />
                <line className="edge lit" x1="350" y1="72" x2="372" y2="236" />
                <line className="edge" x1="230" y1="165" x2="230" y2="298" />
                <circle className="node" cx="230" cy="165" r="13" fill="var(--amber)" stroke="var(--ink)" strokeWidth="1.5" />
                <text x="230" y="143" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">DSA Core · 78%</text>
                <circle cx="110" cy="72" r="11" fill="var(--mastered)" />
                <text x="110" y="50" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Sliding Window · 92%</text>
                <circle cx="350" cy="72" r="11" fill="var(--improving)" />
                <text x="350" y="50" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Dynamic Prog · 41%</text>
                <circle cx="92" cy="228" r="11" fill="var(--mastered)" />
                <text x="92" y="256" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Two Pointers · 88%</text>
                <circle cx="372" cy="236" r="11" fill="var(--improving)" />
                <text x="372" y="264" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Graphs · 55%</text>
                <circle cx="230" cy="298" r="11" fill="var(--focus)" />
                <text x="230" y="326" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">System Design · 30%</text>
              </svg>
              <div className="legend">
                <span><i style={{ background: 'var(--mastered)' }} /> mastered</span>
                <span><i style={{ background: 'var(--improving)' }} /> improving</span>
                <span><i style={{ background: 'var(--focus)' }} /> next focus</span>
              </div>
            </div>
          </div>
        </header>

        {/* PAIN */}
        <section className="pain">
          <div className="wrap">
            <span className="eyebrow">—&nbsp;&nbsp;Sound familiar?</span>
            <h2 style={{ maxWidth: 640 }}>Working hard, but not sure it's adding up?</h2>
            <div className="pain-grid">
              {PAINS.map((p) => (
                <div className="pain-card" key={p.h}>
                  <div className="q">?</div>
                  <h3>{p.h}</h3>
                  <p>{p.p}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* AGENTS */}
        <section id="agents" className="agents">
          <div className="wrap">
            <span className="eyebrow">—&nbsp;&nbsp;Meet your mentor team</span>
            <h2>Five specialists. One mentor who knows you.</h2>
            <p className="section-sub">MentorMan isn't one chatbot — it's a team of focused agents all working from the same picture of you.</p>
            <div className="agent-rows">
              {AGENTS.map((a) => (
                <div className="agent" key={a.role}>
                  <div>
                    <div className="role">{a.role}</div>
                    <h3>{a.h}</h3>
                  </div>
                  <p>{a.desc}</p>
                  <div className="chip">{a.chip}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* MEMORY */}
        <section id="memory" className="memory">
          <div className="bg-grid" aria-hidden="true" style={{ position: 'absolute', inset: 0 }} />
          <img src="/logo-mark.svg" alt="" aria-hidden="true" className="memory-mark" />
          <div className="wrap" style={{ position: 'relative' }}>
            <span className="eyebrow">—&nbsp;&nbsp;Why it works</span>
            <h2>Three layers of memory.<br />You never start over.</h2>
            <p className="section-sub">Most AI tools have goldfish memory. MentorMan is built on a persistent, three-layer memory of who you are, what you know, and everything you've practiced.</p>
            <div className="layer-grid">
              {LAYERS.map((l) => (
                <div className="layer-card" key={l.tag}>
                  <span className="tag">{l.tag}</span>
                  <h3>{l.h}</h3>
                  <p>{l.p}</p>
                  <div className="example">{l.example}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* HOW */}
        <section id="how" className="how">
          <div className="wrap">
            <span className="eyebrow">—&nbsp;&nbsp;How it works</span>
            <h2>From goal to offer, four simple moves</h2>
            <div className="step-grid">
              {STEPS.map((s) => (
                <div className="step-card" key={s.num}>
                  <span className="num">{s.num}</span>
                  <h3>{s.h}</h3>
                  <p>{s.p}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* COMPARE */}
        <section className="compare">
          <div className="wrap">
            <span className="eyebrow">—&nbsp;&nbsp;The difference</span>
            <h2>Stop restarting. Start building.</h2>
            <div className="compare-grid">
              <div className="compare-col old">
                <h3>Prep without a mentor</h3>
                <ul>
                  {COMPARE_OLD.map((t) => (
                    <li key={t}><span className="mark">✕</span>{t}</li>
                  ))}
                </ul>
              </div>
              <div className="compare-col new">
                <h3>Prep with MentorMan</h3>
                <ul>
                  {COMPARE_NEW.map((t) => (
                    <li key={t}><span className="mark">✓</span>{t}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* FINAL CTA */}
        <section className="final-cta">
          <div className="inner">
            <span className="eyebrow">Ready when you are</span>
            <h2>Your next session picks up<br />where this one leaves off.</h2>
            <p>Set your goal today. Your mentor will remember it tomorrow — and every day until your offer.</p>
            <Link to="/register" className="btn btn-primary btn-lg">Start my prep plan <span className="arrow">→</span></Link>
          </div>
        </section>

        {/* FOOTER */}
        <footer>
          <div className="wrap footer-inner">
            <a href="#top" className="logo"><img src="/logo-full.svg" alt="MentorMan" className="footer-logo" /></a>
            <div className="footer-links">
              <a href="#agents">Features</a>
              <a href="#how">How it works</a>
              <a href="#memory">Why it works</a>
            </div>
            <span className="footer-copy">© 2026 MentorMan · mentorman.co.in</span>
          </div>
        </footer>

      </div>
    </div>
  );
}
