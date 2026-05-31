// MentorMan — data, types, constants

export type MessageItem = {
  who: 'mentor' | 'user' | 'verdict';
  text: string;
  label?: string;
  nudge?: string;
  code?: string;
  tone?: 'strong' | 'partial' | 'weak';
  _id?: string;
};

export type Session = {
  id: string;
  title: string;
  cat: string;
  date: string;
  live?: boolean;
};

export type Topic = {
  name: string;
  cat: string;
  cur: number;
  req: number;
  last: string;
  gap: number;
  level: string;
  strong: string[];
  weak: string[];
};

export type ModeId = 'planning' | 'topic' | 'doubt' | 'evaluation';
export type ToneId = 'tough' | 'balanced' | 'encouraging';
export type DensityId = 'compact' | 'cozy' | 'comfy';

export const MODES: { id: ModeId; label: string; blurb: string }[] = [
  { id: 'planning',   label: 'Planning',   blurb: 'Map the roadmap to your goal — milestones, sequencing, pace.' },
  { id: 'topic',      label: 'Topic',      blurb: 'Deep-dive one subject. Warmups, variants, escalating difficulty.' },
  { id: 'doubt',      label: 'Doubt',      blurb: 'Bring a specific problem. Quick unblock, no long detours.' },
  { id: 'evaluation', label: 'Evaluation', blurb: 'Get tested. Q → graded verdict → adjusted difficulty → score.' },
];

export const SESSIONS: Session[] = [
  { id: 's1', title: 'Graphs — BFS/DFS warmups',        cat: 'Topic',    date: 'today',     live: true },
  { id: 's2', title: 'IAM roles for cross-account',     cat: 'Doubt',    date: 'yesterday' },
  { id: 's3', title: 'Topological sort — interview qs', cat: 'Topic',    date: '2d' },
  { id: 's4', title: '6-week FAANG ramp plan',          cat: 'Planning', date: '3d' },
  { id: 's7', title: 'Weekly evaluation — week 3',      cat: 'Eval',     date: '1w' },
  { id: 's5', title: 'Why does my DP solution TLE?',    cat: 'Doubt',    date: '5d' },
  { id: 's8', title: 'Dijkstra on weighted DAGs',       cat: 'Topic',    date: '2w' },
];

export const TOPICS: Topic[] = [
  { name: 'Arrays',         cat: 'DSA',   cur: 85, req: 95, last: '1d ago',   gap: 10, level: 'medium → hard',  strong: ['two pointers','sliding window'], weak: ['prefix sums'] },
  { name: 'Graphs',         cat: 'DSA',   cur: 45, req: 85, last: 'today',    gap: 40, level: 'easy → hard',    strong: ['BFS basics'], weak: ['Dijkstra','union-find','topo sort'] },
  { name: 'Dynamic Prog.',  cat: 'DSA',   cur: 35, req: 80, last: '3d ago',   gap: 45, level: 'easy → hard',    strong: [], weak: ['memoization','state design','knapsack'] },
  { name: 'System Design',  cat: 'Core',  cur: 25, req: 70, last: '2w ago',   gap: 45, level: 'novice → mid',   strong: [], weak: ['load balancing','caching','sharding'] },
  { name: 'AWS',            cat: 'Cloud', cur: 60, req: 75, last: 'yesterday',gap: 15, level: 'mid → senior',   strong: ['IAM','S3'], weak: ['VPC peering'] },
  { name: 'OS',             cat: 'Core',  cur: 55, req: 80, last: '5d ago',   gap: 25, level: 'mid → senior',   strong: ['threads'], weak: ['paging','replacement'] },
];

export const SEEDS: Record<string, MessageItem[]> = {
  s1: [
    { who: 'mentor', text: "Picking up from yesterday — you said BFS still feels rote. Let's do one warmup, then I'll throw a variant at you that breaks the obvious approach." },
    { who: 'user', text: "ok hit me" },
    { who: 'mentor', text: "Classic: **shortest path in an unweighted grid with walls**. Don't code yet — write the function signature, then talk me through your queue invariant.",
      nudge: "When you can state the invariant *before* coding, the code writes itself. That's the muscle we're building." },
    { who: 'user', text: "`def shortest(grid, start, end)` — BFS with a queue of (cell, dist). Invariant: every cell I pop is at the minimum distance from start, because I expand layer by layer." },
    { who: 'mentor', text: "That's exactly it — and you named *why* it's minimal, which is the part most people skip. Now the twist: add one **portal** that teleports A→B at zero cost. Does plain BFS still find the shortest path?" },
  ],
  s4: [
    { who: 'mentor', text: "Let's build your roadmap. You've got **10 weeks** and ~18 hrs/week. Your biggest gaps right now are Graphs (40%) and DP (45%). I'd front-load those while motivation is high." },
    { who: 'user', text: "makes sense. how should I split the weeks?" },
    { who: 'mentor', text: "Rough cut:\n**Wks 1–3** Graphs → DP (the two killers)\n**Wks 4–6** System design + OS\n**Wks 7–8** Mixed mocks, full-length\n**Wks 9–10** Weak-area patching + behavioral.\n\nWe re-plan every Sunday based on your skill graph. Want me to lock week 1?",
      nudge: "Plans aren't promises — they're hypotheses. We adjust every week from real evaluation data, not vibes." },
  ],
  s2: [
    { who: 'user', text: "I keep getting AccessDenied assuming a role in another account. The trust policy looks right to me." },
    { who: 'mentor', text: "Two-sided handshake — both sides have to agree. Account B's role needs Account A in its **trust policy** (you have that), *and* Account A's IAM user/role needs an explicit `sts:AssumeRole` permission pointing at B's role ARN. Which side did you set?" },
    { who: 'user', text: "ohh I only did the trust policy on B. not the sts:AssumeRole on A" },
    { who: 'mentor', text: "That's your gap. Add an inline policy on the A-side principal allowing `sts:AssumeRole` on `arn:aws:iam::B:role/...`. Want the exact JSON?" },
  ],
  s3: [
    { who: 'mentor', text: "Topological sort comes up disguised. Before patterns — when is a topo order even **possible**?" },
    { who: 'user', text: "only on a DAG. if there's a cycle there's no valid ordering" },
    { who: 'mentor', text: "Right. So Kahn's algorithm doubles as a **cycle detector** — if you can't drain all nodes to in-degree 0, there's a cycle. That's the interview move: 'detect if the schedule is feasible' is secretly topo sort. Ready for a real one?" },
  ],
  s5: [
    { who: 'user', text: "my DP solution is correct but it TLEs on the big cases. recursion + memo." },
    { who: 'mentor', text: "Correct-but-slow memo usually means one of two things: you're memoizing on a key that's **too wide** (so cache never hits), or you're recomputing inside each call. Paste the state — what are your memo dimensions?",
      code: "<span class='com'># suspect: memo keyed on a list/slice → unhashable or huge</span>\n<span class='kw'>@cache</span>\n<span class='kw'>def</span> <span class='fn'>solve</span>(i, remaining_tuple): ..." },
  ],
  s8: [
    { who: 'mentor', text: "Dijkstra on a **DAG** is overkill — and it forbids negative weights. On a DAG you can do better. What's the trick?" },
    { who: 'user', text: "topological order then relax edges in that order?" },
    { who: 'mentor', text: "Exactly — **O(V+E)**, beats Dijkstra's O(E log V), *and* it handles negative weights since a DAG has no cycles. You just earned a difficulty bump." },
  ],
};

export const EVAL_SEED: MessageItem[] = [
  { who: 'mentor', text: "Let's evaluate Graphs. I'll move from recall to depth and grade each answer, adjusting difficulty as we go." },
  { who: 'mentor', label: 'Q1 · recall', text: "Walk me through how BFS works on an unweighted graph." },
  { who: 'user', text: "Queue. Push start, mark visited. Pop, expand unvisited neighbors, push + mark. Repeat. Tracks shortest unweighted distance because each layer is one edge deeper." },
  { who: 'verdict', tone: 'strong', label: 'Q1 · recall', text: "Crisp. You named the invariant — one edge per layer — which is the part most people skip. Going deeper." },
  { who: 'mentor', label: 'Q2 · application', text: "You have a grid with walls and one portal teleporting A→B at zero cost. Does plain BFS still find shortest path? If not, what breaks and what's the smallest fix?" },
  { who: 'user', text: "I think BFS still works because the portal is cost 0 so it's just another edge. add B to A's neighbors." },
  { who: 'verdict', tone: 'partial', label: 'Q2 · application', text: "Right instinct — but 'cost 0' is the trap. Plain BFS assumes uniform edge weight. With a zero-cost edge you need 0-1 BFS (a deque) or you'll overcount layers. Flagging this for a session. Moving on." },
];

export const EVAL_DONE_EXTRA: MessageItem[] = [
  { who: 'mentor', label: 'Q5 · synthesis', text: "Last one. When would you reach for 0-1 BFS over Dijkstra, and why does it matter?" },
  { who: 'user', text: "when all weights are 0 or 1 — 0-1 BFS is O(V+E) with a deque vs Dijkstra's O(E log V). same answer, less overhead." },
  { who: 'verdict', tone: 'strong', label: 'Q5 · synthesis', text: "That's the senior answer — you connected the constraint to the complexity. Solid finish." },
];

export function mentorSystemPrompt(mode: ModeId, tone: ToneId, sessionTitle: string): string {
  const toneLine: Record<ToneId, string> = {
    tough:       "Your tone is demanding and direct. Don't coddle. Push for precision, call out hand-waving, raise the bar.",
    balanced:    "Your tone is warm but rigorous — encouraging when earned, honest when not.",
    encouraging: "Your tone is supportive and motivating. Build confidence, celebrate small wins, stay gentle.",
  };
  const modeLine: Record<ModeId, string> = {
    planning:   "MODE: Planning. Help structure a roadmap — milestones, sequencing, realistic pace. Think in weeks.",
    topic:      "MODE: Topic. Teach by Socratic questioning. Ask before you tell. Escalate difficulty as they succeed.",
    doubt:      "MODE: Doubt. Unblock a specific problem fast and precisely. No long detours.",
    evaluation: "MODE: Evaluation. You are testing them. Ask one focused question, grade their last answer briefly, then probe deeper.",
  };
  return `You are MentorMan, an AI mentor coaching a software engineer toward a FAANG-level SWE role. ${modeLine[mode]} ${toneLine[tone]}
Keep replies SHORT — 2-4 sentences, like a real chat. Use a Socratic style: prefer asking a sharp follow-up over lecturing. You may use **bold** for key terms and \`code\` for identifiers. Current session: "${sessionTitle}". Never break character or mention being an AI model.`;
}

export const ACCENTS: Record<string, { ink: string }> = {
  '#34d399': { ink: '#04140d' },
  '#5b9bff': { ink: '#04122e' },
  '#a78bfa': { ink: '#180a36' },
  '#fbbf24': { ink: '#2e1f02' },
  '#fb7185': { ink: '#2e0712' },
};

export const catToMode: Record<string, ModeId> = {
  Topic: 'topic', Doubt: 'doubt', Planning: 'planning', Eval: 'evaluation'
};
