import { useEffect } from 'react';
import { Link } from 'react-router-dom';

const TITLE = 'MentorMan — The AI mentor that remembers you';
const DESCRIPTION =
  "MentorMan turns your goal, your gaps, and every session into a personal interview-prep roadmap. Socratic teaching, targeted drills, and a mentor that never forgets where you left off.";

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

export function LandingPage() {
  useDocumentHead(TITLE, DESCRIPTION);

  return (
    <div className="mm-landing">
      <style>{`
.mm-landing{
  --paper:#F5F7FA;
  --paper-2:#EDF1F6;
  --ink:#141F33;
  --ink-soft:#44526B;
  --blue:#2B4C9B;
  --blue-deep:#1B3168;
  --signal:#0E9384;      /* teal — mastery / growth */
  --amber:#D77E1E;       /* in-progress */
  --line:#D4DCE7;
  --grid:#E3E9F1;
  --radius:14px;
  --maxw:1120px;
  --lp-display:'Bricolage Grotesque',sans-serif;
  --lp-body:'IBM Plex Sans',sans-serif;
  --lp-mono:'IBM Plex Mono',monospace;
}
.mm-landing *{margin:0;padding:0;box-sizing:border-box}
.mm-landing{
  font-family:var(--lp-body);
  color:var(--ink);
  background:var(--paper);
  background-image:
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:32px 32px;
  line-height:1.6;
  -webkit-font-smoothing:antialiased;
  scroll-behavior:smooth;
}
.mm-landing img,.mm-landing svg{display:block;max-width:100%}
.mm-landing a{color:inherit;text-decoration:none}
.mm-landing .wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
.mm-landing .eyebrow{
  font-family:var(--lp-mono);font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--blue);
  display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;
}
.mm-landing .eyebrow::before{content:"";width:22px;height:1px;background:var(--blue)}
.mm-landing h1,.mm-landing h2,.mm-landing h3{font-family:var(--lp-display);line-height:1.12;letter-spacing:-.015em}
.mm-landing h2{font-size:clamp(28px,4vw,42px);font-weight:700}
.mm-landing .section{padding:96px 0}
.mm-landing .section-sub{color:var(--ink-soft);max-width:560px;margin-top:14px;font-size:17px}

/* ---------- Nav ---------- */
.mm-landing .nav{
  position:sticky;top:0;z-index:50;
  background:rgba(245,247,250,.85);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line);
}
.mm-landing .nav-inner{display:flex;align-items:center;justify-content:space-between;height:64px}
.mm-landing .logo{font-family:var(--lp-display);font-weight:800;font-size:20px;display:flex;align-items:center;gap:9px}
.mm-landing .logo-mark{
  width:28px;height:28px;border-radius:8px;background:var(--blue);
  display:grid;place-items:center;color:#fff;font-family:var(--lp-mono);font-size:13px;font-weight:500;
}
.mm-landing .nav-links{display:flex;gap:28px;font-size:14.5px;font-weight:500;color:var(--ink-soft)}
.mm-landing .nav-links a:hover{color:var(--ink)}
.mm-landing .nav-cta{display:flex;gap:12px;align-items:center}
.mm-landing .btn{
  display:inline-flex;align-items:center;gap:8px;
  font-family:var(--lp-body);font-weight:600;font-size:15px;
  padding:11px 22px;border-radius:10px;border:1px solid transparent;
  cursor:pointer;transition:transform .15s ease, box-shadow .15s ease, background .15s ease;
}
.mm-landing .btn-primary{background:var(--blue);color:#fff;box-shadow:0 4px 14px rgba(43,76,155,.28)}
.mm-landing .btn-primary:hover{background:var(--blue-deep);transform:translateY(-1px)}
.mm-landing .btn-ghost{border-color:var(--line);background:#fff;color:var(--ink)}
.mm-landing .btn-ghost:hover{border-color:var(--blue)}
.mm-landing .btn .arrow{transition:transform .15s ease}
.mm-landing .btn:hover .arrow{transform:translateX(3px)}

/* ---------- Hero ---------- */
.mm-landing .hero{padding:88px 0 72px;position:relative;overflow:hidden}
.mm-landing .hero-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:56px;align-items:center}
.mm-landing .hero h1{font-size:clamp(38px,5.4vw,60px);font-weight:800}
.mm-landing .hero h1 .hl{color:var(--blue);position:relative;white-space:nowrap}
.mm-landing .hero h1 .hl::after{
  content:"";position:absolute;left:0;right:0;bottom:6px;height:10px;
  background:rgba(14,147,132,.22);z-index:-1;border-radius:3px;
}
.mm-landing .hero p.lead{margin-top:20px;font-size:18px;color:var(--ink-soft);max-width:520px}
.mm-landing .hero-ctas{display:flex;gap:14px;margin-top:32px;flex-wrap:wrap}
.mm-landing .hero-note{margin-top:14px;font-family:var(--lp-mono);font-size:12.5px;color:var(--ink-soft)}
.mm-landing .badge{
  display:inline-flex;align-items:center;gap:8px;
  font-family:var(--lp-mono);font-size:12px;color:var(--blue-deep);
  background:#fff;border:1px solid var(--line);border-radius:100px;
  padding:6px 14px;margin-bottom:22px;
}
.mm-landing .badge .dot{width:7px;height:7px;border-radius:50%;background:var(--signal);animation:mm-pulse 2s infinite}
@keyframes mm-pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* skill graph card */
.mm-landing .graph-card{
  background:#fff;border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:0 20px 50px rgba(20,31,51,.10);
  padding:20px;position:relative;
}
.mm-landing .graph-card .card-head{
  display:flex;justify-content:space-between;align-items:center;
  font-family:var(--lp-mono);font-size:12px;color:var(--ink-soft);
  padding-bottom:14px;border-bottom:1px dashed var(--line);margin-bottom:8px;
}
.mm-landing .legend{display:flex;gap:16px;font-family:var(--lp-mono);font-size:11.5px;color:var(--ink-soft);padding-top:12px;border-top:1px dashed var(--line);margin-top:6px}
.mm-landing .legend span{display:inline-flex;align-items:center;gap:6px}
.mm-landing .legend i{width:9px;height:9px;border-radius:50%}
.mm-landing .node{cursor:default}
.mm-landing .node circle{transition:r .2s ease}
.mm-landing .node:hover circle.core{r:15}
.mm-landing .node text{font-family:var(--lp-mono);font-size:10.5px;fill:var(--ink-soft)}
.mm-landing .edge{stroke:var(--line);stroke-width:1.4}
.mm-landing .edge.lit{stroke:var(--signal);stroke-dasharray:4 4;animation:mm-dash 3s linear infinite}
@keyframes mm-dash{to{stroke-dashoffset:-40}}

/* ---------- Pain ---------- */
.mm-landing .pain{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.mm-landing .pain-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:44px}
.mm-landing .pain-card{
  border:1px solid var(--line);border-radius:var(--radius);padding:26px 22px;background:var(--paper);
}
.mm-landing .pain-card .q{font-family:var(--lp-mono);font-size:22px;color:var(--amber);margin-bottom:12px}
.mm-landing .pain-card h3{font-size:17px;margin-bottom:8px}
.mm-landing .pain-card p{font-size:14.5px;color:var(--ink-soft);font-style:italic}

/* ---------- Agents / features ---------- */
.mm-landing .agent-rows{margin-top:52px;display:flex;flex-direction:column;gap:18px}
.mm-landing .agent{
  display:grid;grid-template-columns:200px 1fr 320px;gap:28px;align-items:center;
  background:#fff;border:1px solid var(--line);border-radius:var(--radius);
  padding:26px 30px;transition:box-shadow .2s ease, transform .2s ease;
}
.mm-landing .agent:hover{box-shadow:0 12px 34px rgba(20,31,51,.08);transform:translateY(-2px)}
.mm-landing .agent .role{font-family:var(--lp-mono);font-size:12px;color:var(--blue);letter-spacing:.1em;text-transform:uppercase}
.mm-landing .agent h3{font-size:20px;margin-top:6px}
.mm-landing .agent .desc{color:var(--ink-soft);font-size:15px}
.mm-landing .agent .chip{
  justify-self:end;font-family:var(--lp-mono);font-size:12.5px;color:var(--blue-deep);
  background:var(--paper-2);border:1px solid var(--line);border-radius:8px;padding:10px 14px;
}

/* ---------- Memory (signature section) ---------- */
.mm-landing .memory{background:var(--ink);color:#EAF0F8;position:relative;overflow:hidden}
.mm-landing .memory::before{
  content:"";position:absolute;inset:0;
  background-image:
    linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px);
  background-size:32px 32px;
}
.mm-landing .memory .wrap{position:relative}
.mm-landing .memory .eyebrow{color:var(--signal)}
.mm-landing .memory .eyebrow::before{background:var(--signal)}
.mm-landing .memory h2{color:#fff}
.mm-landing .memory .section-sub{color:#A9B7CC}
.mm-landing .layers{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:52px}
.mm-landing .layer{
  border:1px solid rgba(255,255,255,.14);border-radius:var(--radius);
  padding:28px 24px;background:rgba(255,255,255,.04);
}
.mm-landing .layer .tag{font-family:var(--lp-mono);font-size:11.5px;color:var(--signal);letter-spacing:.12em}
.mm-landing .layer h3{color:#fff;font-size:19px;margin:10px 0 10px}
.mm-landing .layer p{font-size:14.5px;color:#A9B7CC}
.mm-landing .layer .example{
  margin-top:18px;font-family:var(--lp-mono);font-size:12px;color:#C8D4E4;
  background:rgba(255,255,255,.06);border-left:2px solid var(--signal);
  padding:10px 14px;border-radius:0 8px 8px 0;
}

/* ---------- How it works ---------- */
.mm-landing .steps{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:52px}
.mm-landing .step{
  background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:28px 24px;position:relative;
}
.mm-landing .step .num{
  font-family:var(--lp-mono);font-size:12px;color:var(--blue);
  border:1px solid var(--line);border-radius:100px;padding:4px 12px;display:inline-block;margin-bottom:16px;
}
.mm-landing .step h3{font-size:17.5px;margin-bottom:8px}
.mm-landing .step p{font-size:14.5px;color:var(--ink-soft)}

/* ---------- Compare ---------- */
.mm-landing .compare{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.mm-landing .compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:48px}
.mm-landing .compare-col{border-radius:var(--radius);padding:32px}
.mm-landing .compare-col.old{border:1px dashed var(--line);background:var(--paper)}
.mm-landing .compare-col.new{border:1px solid var(--blue);background:linear-gradient(180deg,#FBFCFE, #F1F5FB)}
.mm-landing .compare-col h3{font-size:19px;margin-bottom:20px}
.mm-landing .compare-col ul{list-style:none;display:flex;flex-direction:column;gap:14px}
.mm-landing .compare-col li{display:flex;gap:12px;align-items:flex-start;font-size:15px}
.mm-landing .mark{font-family:var(--lp-mono);font-size:14px;line-height:1.6;flex-shrink:0}
.mm-landing .old .mark{color:#C4453B}
.mm-landing .new .mark{color:var(--signal)}
.mm-landing .old li{color:var(--ink-soft)}

/* ---------- FAQ ---------- */
.mm-landing .faq-list{margin-top:44px;max-width:760px}
.mm-landing details{border-bottom:1px solid var(--line);padding:22px 4px}
.mm-landing details summary{
  cursor:pointer;list-style:none;font-family:var(--lp-display);font-weight:600;font-size:17.5px;
  display:flex;justify-content:space-between;align-items:center;gap:16px;
}
.mm-landing details summary::-webkit-details-marker{display:none}
.mm-landing details summary::after{content:"+";font-family:var(--lp-mono);color:var(--blue);font-size:20px;transition:transform .2s}
.mm-landing details[open] summary::after{transform:rotate(45deg)}
.mm-landing details p{margin-top:14px;color:var(--ink-soft);font-size:15.5px;max-width:640px}

/* ---------- Final CTA ---------- */
.mm-landing .final{padding:110px 0;text-align:center}
.mm-landing .final h2{font-size:clamp(30px,4.6vw,48px)}
.mm-landing .final p{margin:16px auto 34px;max-width:520px;color:var(--ink-soft);font-size:17px}

/* ---------- Footer ---------- */
.mm-landing footer{border-top:1px solid var(--line);background:#fff;padding:48px 0}
.mm-landing .foot{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:20px}
.mm-landing .foot .small{font-family:var(--lp-mono);font-size:12.5px;color:var(--ink-soft)}
.mm-landing .foot-links{display:flex;gap:24px;font-size:14px;color:var(--ink-soft)}
.mm-landing .foot-links a:hover{color:var(--ink)}

/* ---------- Responsive ---------- */
@media (max-width:960px){
  .mm-landing .hero-grid{grid-template-columns:1fr}
  .mm-landing .pain-grid,.mm-landing .steps{grid-template-columns:repeat(2,1fr)}
  .mm-landing .layers{grid-template-columns:1fr}
  .mm-landing .agent{grid-template-columns:1fr;gap:12px}
  .mm-landing .agent .chip{justify-self:start}
  .mm-landing .compare-grid{grid-template-columns:1fr}
  .mm-landing .nav-links{display:none}
}
@media (max-width:560px){
  .mm-landing .pain-grid,.mm-landing .steps{grid-template-columns:1fr}
  .mm-landing .section{padding:68px 0}
}
@media (prefers-reduced-motion:reduce){
  .mm-landing *,.mm-landing *::before,.mm-landing *::after{animation:none!important;transition:none!important}
}
      `}</style>

      {/* NAV */}
      <nav className="nav">
        <div className="wrap nav-inner">
          <a href="#" className="logo"><span className="logo-mark">M</span>MentorMan</a>
          <div className="nav-links">
            <a href="#agents">Features</a>
            <a href="#memory">Why it works</a>
            <a href="#how">How it works</a>
            <a href="#faq">FAQ</a>
          </div>
          <div className="nav-cta">
            <Link to="/login" className="btn btn-ghost">Sign in</Link>
            <Link to="/register" className="btn btn-primary">Start free <span className="arrow">→</span></Link>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <header className="hero">
        <div className="wrap hero-grid">
          <div>
            <span className="badge"><span className="dot"></span> Goal-aware interview prep</span>
            <h1>Interview prep with a mentor that <span className="hl">remembers you</span></h1>
            <p className="lead">MentorMan learns your goal, maps your skill gaps, and remembers every session — so each lesson, drill, and review picks up exactly where your last one left off.</p>
            <div className="hero-ctas">
              <Link to="/register" className="btn btn-primary">Start my prep plan <span className="arrow">→</span></Link>
              <a href="#how" className="btn btn-ghost">See how it works</a>
            </div>
            <p className="hero-note">Free to start · No credit card required</p>
          </div>

          {/* Signature: live skill graph */}
          <div className="graph-card" aria-label="Example skill graph showing topic mastery">
            <div className="card-head">
              <span>skill-graph · gopi@mentorman</span>
              <span>updated after last session</span>
            </div>
            <svg viewBox="0 0 460 330" role="img" aria-label="Skill graph with connected topics">
              <line className="edge lit" x1="230" y1="160" x2="110" y2="70"/>
              <line className="edge" x1="230" y1="160" x2="350" y2="70"/>
              <line className="edge lit" x1="230" y1="160" x2="90" y2="220"/>
              <line className="edge" x1="230" y1="160" x2="370" y2="230"/>
              <line className="edge" x1="110" y1="70" x2="90" y2="220"/>
              <line className="edge lit" x1="350" y1="70" x2="370" y2="230"/>
              <line className="edge" x1="230" y1="160" x2="230" y2="290"/>

              <g className="node">
                <circle className="core" cx="230" cy="160" r="13" fill="#2B4C9B"/>
                <text x="230" y="138" textAnchor="middle">DSA Core · 78%</text>
              </g>
              <g className="node">
                <circle className="core" cx="110" cy="70" r="11" fill="#0E9384"/>
                <text x="110" y="48" textAnchor="middle">Sliding Window · 92%</text>
              </g>
              <g className="node">
                <circle className="core" cx="350" cy="70" r="11" fill="#D77E1E"/>
                <text x="350" y="48" textAnchor="middle">Dynamic Prog · 41%</text>
              </g>
              <g className="node">
                <circle className="core" cx="90" cy="220" r="11" fill="#0E9384"/>
                <text x="90" y="248" textAnchor="middle">Two Pointers · 88%</text>
              </g>
              <g className="node">
                <circle className="core" cx="370" cy="230" r="11" fill="#D77E1E"/>
                <text x="370" y="258" textAnchor="middle">Graphs · 55%</text>
              </g>
              <g className="node">
                <circle className="core" cx="230" cy="290" r="11" fill="#C4453B"/>
                <text x="230" y="316" textAnchor="middle">System Design · 30%</text>
              </g>
            </svg>
            <div className="legend">
              <span><i style={{ background: '#0E9384' }}></i> mastered</span>
              <span><i style={{ background: '#D77E1E' }}></i> improving</span>
              <span><i style={{ background: '#C4453B' }}></i> next focus</span>
            </div>
          </div>
        </div>
      </header>

      {/* PAIN */}
      <section className="section pain">
        <div className="wrap">
          <span className="eyebrow">Sound familiar?</span>
          <h2>Grinding hard, but going in circles</h2>
          <div className="pain-grid">
            <div className="pain-card">
              <div className="q">?</div>
              <h3>No real plan</h3>
              <p>"I solved 300 LeetCode problems… randomly. Am I even ready?"</p>
            </div>
            <div className="pain-card">
              <div className="q">?</div>
              <h3>Same mistakes, again</h3>
              <p>"I keep messing up the same edge cases in every mock interview."</p>
            </div>
            <div className="pain-card">
              <div className="q">?</div>
              <h3>Tools that forget you</h3>
              <p>"Every chat starts from zero. I re-explain my situation every single time."</p>
            </div>
            <div className="pain-card">
              <div className="q">?</div>
              <h3>System design guesswork</h3>
              <p>"I can code, but designing a system in 45 minutes? No idea where to start."</p>
            </div>
          </div>
        </div>
      </section>

      {/* AGENTS */}
      <section className="section" id="agents">
        <div className="wrap">
          <span className="eyebrow">Meet your mentor team</span>
          <h2>Five specialists. One mentor. Your goal.</h2>
          <p className="section-sub">MentorMan isn't one chatbot — it's a team of focused agents working from the same picture of you.</p>

          <div className="agent-rows">
            <div className="agent">
              <div><div className="role">Profiler</div><h3>Knows you</h3></div>
              <p className="desc">Builds your profile from your resume, target companies, and practice history — your goal, timeline, and current level, always up to date.</p>
              <div className="chip">goal: Senior SWE · Aug 2026</div>
            </div>
            <div className="agent">
              <div><div className="role">Planner</div><h3>Charts the path</h3></div>
              <p className="desc">Turns your goal into a week-by-week roadmap, re-prioritized after every session based on what's actually improving.</p>
              <div className="chip">this week: Graphs → BFS patterns</div>
            </div>
            <div className="agent">
              <div><div className="role">Teacher</div><h3>Teaches Socratically</h3></div>
              <p className="desc">Explains with questions, analogies, and visuals — guiding you to the insight instead of dumping the answer on you.</p>
              <div className="chip">"What happens if the window shrinks?"</div>
            </div>
            <div className="agent">
              <div><div className="role">Quizzer</div><h3>Drills your gaps</h3></div>
              <p className="desc">Generates problems and MCQs aimed precisely at your weak spots, with instant feedback and spaced follow-ups.</p>
              <div className="chip">drill: DP on strings · 5 Qs</div>
            </div>
            <div className="agent">
              <div><div className="role">Reviewer</div><h3>Tracks your mistakes</h3></div>
              <p className="desc">Logs every slip — off-by-one, missed edge case, wrong data structure — and resurfaces it before it costs you an interview.</p>
              <div className="chip">recurring: forgot empty-input check ×3</div>
            </div>
          </div>
        </div>
      </section>

      {/* MEMORY */}
      <section className="section memory" id="memory">
        <div className="wrap">
          <span className="eyebrow">Why it works</span>
          <h2>Three layers of memory.<br/>Zero starting over.</h2>
          <p className="section-sub">Most AI tools have goldfish memory. MentorMan is built on a persistent, three-layer memory of who you are, what you know, and everything you've practiced.</p>

          <div className="layers">
            <div className="layer">
              <span className="tag">LAYER 1 — CORE PROFILE</span>
              <h3>Your goal, always in view</h3>
              <p>Your target role, companies, timeline, and constraints anchor every conversation. Nothing you're taught is off-path.</p>
              <div className="example">target: Senior SWE, product cos<br/>timeline: Aug 2026</div>
            </div>
            <div className="layer">
              <span className="tag">LAYER 2 — SKILL GRAPH</span>
              <h3>A live map of your skills</h3>
              <p>Every topic — arrays to system design — scored and connected. Your mentor always knows what to teach next and what to skip.</p>
              <div className="example">sliding_window: 92% ✓<br/>dynamic_programming: 41% ⚠</div>
            </div>
            <div className="layer">
              <span className="tag">LAYER 3 — EPISODIC MEMORY</span>
              <h3>Every session, remembered</h3>
              <p>Past explanations, questions you asked, mistakes you made — recalled when relevant, so lessons build on each other.</p>
              <div className="example">recall: "we compared this to the<br/>Swiggy delivery-batching example"</div>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="section" id="how">
        <div className="wrap">
          <span className="eyebrow">How it works</span>
          <h2>From goal to offer, in four moves</h2>
          <div className="steps">
            <div className="step">
              <span className="num">01</span>
              <h3>Share your goal</h3>
              <p>Upload your resume, pick your target role and companies, and set your timeline. That's your Core Profile.</p>
            </div>
            <div className="step">
              <span className="num">02</span>
              <h3>Get your roadmap</h3>
              <p>The Planner builds a week-by-week prep plan from your skill graph — focused on your real gaps, not a generic syllabus.</p>
            </div>
            <div className="step">
              <span className="num">03</span>
              <h3>Learn by thinking</h3>
              <p>Socratic lessons per topic, in persistent threads. Come back tomorrow and continue mid-thought — no recap needed.</p>
            </div>
            <div className="step">
              <span className="num">04</span>
              <h3>Drill, review, repeat</h3>
              <p>Targeted quizzes find the gaps, the mistake tracker keeps you honest, and your skill graph updates after every session.</p>
            </div>
          </div>
        </div>
      </section>

      {/* COMPARE */}
      <section className="section compare">
        <div className="wrap">
          <span className="eyebrow">The difference</span>
          <h2>Stop restarting. Start compounding.</h2>
          <div className="compare-grid">
            <div className="compare-col old">
              <h3>Prep without a mentor</h3>
              <ul>
                <li><span className="mark">✕</span> Random problem grinding with no direction</li>
                <li><span className="mark">✕</span> Chatbots that forget you between sessions</li>
                <li><span className="mark">✕</span> Re-reading answers instead of thinking</li>
                <li><span className="mark">✕</span> Mistakes repeated until interview day</li>
                <li><span className="mark">✕</span> No idea if you're actually ready</li>
              </ul>
            </div>
            <div className="compare-col new">
              <h3>Prep with MentorMan</h3>
              <ul>
                <li><span className="mark">✓</span> A roadmap built from your goal and gaps</li>
                <li><span className="mark">✓</span> A mentor that remembers every session</li>
                <li><span className="mark">✓</span> Socratic teaching that makes ideas stick</li>
                <li><span className="mark">✓</span> A mistake tracker that closes weak spots</li>
                <li><span className="mark">✓</span> A live skill graph showing exactly where you stand</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="section" id="faq">
        <div className="wrap">
          <span className="eyebrow">FAQ</span>
          <h2>Questions, answered</h2>
          <div className="faq-list">
            <details open>
              <summary>Who is MentorMan for?</summary>
              <p>Software engineers preparing for interviews — from DSA rounds to system design — who want a structured, personalized plan instead of random grinding. It works whether you're targeting your first job or a senior role.</p>
            </details>
            <details>
              <summary>How is this different from ChatGPT or Claude?</summary>
              <p>General chatbots start from zero every conversation. MentorMan keeps a persistent three-layer memory — your goal, your skill graph, and your full session history — so teaching, drills, and reviews compound over weeks instead of resetting every chat.</p>
            </details>
            <details>
              <summary>What does "Socratic teaching" mean here?</summary>
              <p>Instead of handing you answers, your mentor guides you with questions, hints, and analogies until you reach the insight yourself. It's slower per question and dramatically faster per concept — because what you figure out, you keep.</p>
            </details>
            <details>
              <summary>What can I upload?</summary>
              <p>Your resume and your practice history (like a LeetCode export) to bootstrap your profile and skill graph. From there, MentorMan updates everything automatically as you learn.</p>
            </details>
            <details>
              <summary>Is my data private?</summary>
              <p>Yes. Your profile, skill graph, and session history are yours alone — used only to personalize your mentoring, never shared or sold.</p>
            </details>
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="final">
        <div className="wrap">
          <span className="eyebrow" style={{ justifyContent: 'center' }}>Ready when you are</span>
          <h2>Your next session picks up<br/>where this one leaves off.</h2>
          <p>Set your goal today. Your mentor will remember it tomorrow — and every day until your offer.</p>
          <Link to="/register" className="btn btn-primary" style={{ fontSize: '16px', padding: '14px 28px' }}>Start my prep plan <span className="arrow">→</span></Link>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="wrap foot">
          <a href="#" className="logo" style={{ fontSize: '17px' }}><span className="logo-mark" style={{ width: '24px', height: '24px', fontSize: '11px' }}>M</span>MentorMan</a>
          <div className="foot-links">
            <a href="#agents">Features</a>
            <a href="#how">How it works</a>
            <a href="#faq">FAQ</a>
            <a href="mailto:hello@mentorman.co.in">Contact</a>
          </div>
          <span className="small">© 2026 MentorMan · mentorman.co.in</span>
        </div>
      </footer>
    </div>
  );
}
