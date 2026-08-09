import { useEffect } from 'react';
import { Link } from 'react-router-dom';

const TITLE = 'MentorMan — The AI mentor that remembers you';
const DESCRIPTION =
  "MentorMan turns your goal, your gaps, and every session into a personal study roadmap for any subject. Socratic teaching, targeted drills, and a mentor that never forgets where you left off.";

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

const AGENTS = [
  { role: 'Profiler', h: 'Knows you', desc: "A short onboarding conversation learns why you're here and which topics matter, so lessons start relevant instead of generic.", chip: 'context: learning Spanish · focus: Grammar, Vocabulary' },
  { role: 'Planner', h: 'Charts the path', desc: 'Your topics are mapped as a skill graph, scored as you go, so you and your mentor both know what to focus on next.', chip: 'this week: Verb Tenses → Practice' },
  { role: 'Teacher', h: 'Teaches by asking', desc: "Prompts you to attempt first, then reveals help gradually — a nudge, a hint, a worked step — instead of handing over the answer.", chip: '"Why does the word change here?"' },
  { role: 'Quizzer', h: 'Checks your understanding', desc: 'Switches into a quiz mode that withholds hints, so you get an honest read on what you actually know.', chip: 'drill: Verb Conjugation · 5 Qs' },
];

const STEPS = [
  { num: '01', h: "Tell it what you're learning", p: "A short conversation — what you're studying, which topics matter, how you like to be taught. That is your Core Profile." },
  { num: '02', h: 'Get your roadmap', p: 'The Planner builds a week-by-week plan from your skill graph — focused on your real gaps, not a generic syllabus.' },
  { num: '03', h: 'Learn by thinking', p: 'Socratic lessons per topic, in persistent threads. Come back tomorrow and continue mid-thought — no recap needed.' },
  { num: '04', h: 'Drill, review, repeat', p: 'Targeted quizzes find the gaps, the mistake tracker keeps you honest, and your skill graph updates every session.' },
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

/* ---------- How it works ---------- */
.mm-landing .how{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:96px 24px}
.mm-landing .step-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:52px}
.mm-landing .step-card{background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:28px 24px}
.mm-landing .step-card .num{font-family:var(--lp-mono);font-size:12px;color:var(--accent);border:1px solid var(--line);border-radius:100px;padding:4px 12px;display:inline-block;margin-bottom:16px}
.mm-landing .step-card h3{font-family:var(--lp-display);font-weight:700;font-size:17.5px;margin-bottom:8px}
.mm-landing .step-card p{font-size:14.5px;color:var(--ink-soft)}

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
              <span className="badge"><span className="dot"></span> AI mentor for any subject</span>
              <h1>An AI mentor that <span className="hl">remembers your progress</span></h1>
              <p className="lead">Tell it what you're studying. It builds your roadmap, teaches by asking questions, and quizzes your weak spots — remembering everything so you never start from zero.</p>
              <div className="hero-ctas">
                <Link to="/register" className="btn btn-primary btn-lg">Start learning <span className="arrow">→</span></Link>
                <a href="#how" className="btn btn-ghost btn-lg">See how it works</a>
              </div>
              <p className="hero-note">Free to start, no card needed</p>
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
                <text x="230" y="143" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Spanish · 78%</text>
                <circle cx="110" cy="72" r="11" fill="var(--mastered)" />
                <text x="110" y="50" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Vocabulary · 92%</text>
                <circle cx="350" cy="72" r="11" fill="var(--improving)" />
                <text x="350" y="50" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Verb Tenses · 41%</text>
                <circle cx="92" cy="228" r="11" fill="var(--mastered)" />
                <text x="92" y="256" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Grammar · 88%</text>
                <circle cx="372" cy="236" r="11" fill="var(--improving)" />
                <text x="372" y="264" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Listening · 55%</text>
                <circle cx="230" cy="298" r="11" fill="var(--focus)" />
                <text x="230" y="326" textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">Speaking · 30%</text>
              </svg>
              <div className="legend">
                <span><i style={{ background: 'var(--mastered)' }} /> mastered</span>
                <span><i style={{ background: 'var(--improving)' }} /> improving</span>
                <span><i style={{ background: 'var(--focus)' }} /> next focus</span>
              </div>
            </div>
          </div>
        </header>

        {/* AGENTS */}
        <section id="agents" className="agents">
          <div className="wrap">
            <span className="eyebrow">—&nbsp;&nbsp;How your mentor works</span>
            <h2>One mentor, four things it actually does.</h2>
            <p className="section-sub">Not a generic chatbot — it profiles you, plans your path, teaches by asking, and checks what stuck.</p>
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

        {/* HOW */}
        <section id="how" className="how">
          <div className="wrap">
            <span className="eyebrow">—&nbsp;&nbsp;How it works</span>
            <h2>From goal to mastery, four simple moves</h2>
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

        {/* FINAL CTA */}
        <section className="final-cta">
          <div className="inner">
            <span className="eyebrow">Ready when you are</span>
            <h2>Your next session picks up<br />where this one leaves off.</h2>
            <p>Set your goal today. Your mentor will remember it tomorrow — and every day until you've mastered it.</p>
            <Link to="/register" className="btn btn-primary btn-lg">Start learning <span className="arrow">→</span></Link>
          </div>
        </section>

        {/* FOOTER */}
        <footer>
          <div className="wrap footer-inner">
            <a href="#top" className="logo"><img src="/logo-full.svg" alt="MentorMan" className="footer-logo" /></a>
            <div className="footer-links">
              <a href="#agents">Features</a>
              <a href="#how">How it works</a>
            </div>
            <span className="footer-copy">© 2026 MentorMan · mentorman.co.in</span>
          </div>
        </footer>

      </div>
    </div>
  );
}
