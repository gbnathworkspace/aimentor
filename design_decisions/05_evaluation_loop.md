# Evaluation Loop

## Decision
Combine passive signals (LeetCode history) and active signals
(mentor probing questions) to measure proficiency.

## Why
Self-reported skill levels are unreliable. The system needs to
form its own verdict by observing and testing the user directly.

## Two Signal Types

### Passive — LeetCode history
What's solved, at what difficulty, how recently.
Ingested from CSV export during onboarding and updated each session.
Lower effort but weaker signal — completing problems doesn't prove understanding.

### Active — Mentor probing
The mentor asks questions in increasing depth:

```
1. Recall       "what is BFS?"                    → weak signal
2. Application  "which algorithm for this graph?" → better
3. Depth        "can you beat O(V+E) for this?"   → reveals true level
```

Strong answer → move to harder question
Weak answer   → probe deeper before moving on

## Verdict
At end of evaluation, LLM produces:
```json
{
  "topic": "graphs",
  "eval_score": "3/5",
  "new_current_level": "medium",
  "weak_areas": ["negative weight cycles"],
  "strong_areas": ["BFS", "DFS", "cycle detection"]
}
```

This updates the skill graph node's current_level and gap.

## Conflict handling
When LeetCode signal contradicts mentor eval signal:
Active signal (mentor eval) takes priority — it's higher quality.
LeetCode data is a supporting signal, not the source of truth.

Conflict resolution: mentor eval always wins. No weighting formula.
Active signal is higher quality than passive — no need to blend them.
