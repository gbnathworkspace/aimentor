# Goal Anchoring

## Problem
With a large context window, the goal stated in Layer 1 gets
attention-weighted down by surrounding content — the "lost in the
middle" problem. The LLM answers questions correctly but stops
connecting responses back to what actually matters for the user's goal.

## Three failure modes

```
Topic drift:      session starts on graphs, ends on OS concepts
Episodic noise:   vector search returns loosely related sessions,
                  LLM anchors on them instead of the goal
Recency bias:     last 3 turns dominate reasoning over Layer 1
```

## Fix 1 — Repeat goal at bottom of context (right before user message)

```
...conversation history...

REMINDER: User's goal is 20 LPA by Aug 2026.
10 weeks left. Biggest gap is graphs (40%).
Keep responses tied to this context.

[User message]
```

Costs ~50 tokens. Positions the goal where attention is highest.
Injected every turn automatically.

## Fix 2 — Mentor persona in system prompt

```
"You are a focused mentor, not a tutor.
 A tutor answers every question asked.
 A mentor answers with the goal in mind.
 If the user drifts from priority areas,
 acknowledge the question but redirect
 to what matters most for their goal."
```

Bakes goal-awareness into behaviour, not just context.

## Fix 3 — Drift detection (v2)
Every N turns, a lightweight check:
"Is this conversation aligned with the user's priority gaps?"

- Yes → continue
- No  → surface soft redirect:
        "This is useful, but graphs is your biggest gap —
         want to get back to that?"

Adds latency. v2 feature — not v1.

## Priority of fixes

```
Fix                     Impact    Cost    Version
──────────────────────────────────────────────────
Mentor persona          High      Zero    v1
Goal anchor at bottom   High      50 tok  v1
Drift detection         Medium    Latency v2
```
