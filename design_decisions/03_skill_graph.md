# Skill Graph

## Decision
Proficiency is measured relative to the goal, not in absolute terms.

## Why
A user doesn't need to master graph theory in full — they need what
their specific goal actually demands. The benchmark changes
based on what the user is aiming for.

## Node Structure
```json
{
  "topic": "graphs",
  "current_level": "easy",
  "required_level": "medium",
  "gap": "40%",
  "last_studied": "2026-05-08",
  "signals": {
    "leetcode_solved": { "easy": 10, "medium": 2, "hard": 0 },
    "mentor_eval_score": "3/5",
    "weak_areas": ["negative weight cycles"],
    "strong_areas": ["BFS", "DFS", "cycle detection"]
  }
}
```

## required_level source
Comes from the Goal Knowledge Base — not guessed by the LLM.
The KB stores what each goal actually requires per topic,
sourced from curated, goal-relevant material (syllabi, role expectations, prep sites).

## gap calculation
gap = required_level - current_level
When goal evolves, required_level updates and gap is recalculated.
current_level is never reset — all past progress is preserved.

## Schema is LLM-generated per user
During onboarding, the LLM reads the user's goal and generates
the initial set of topic nodes. The developer is not in the loop
for per-user schema decisions.
