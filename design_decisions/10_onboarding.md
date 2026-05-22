# Onboarding Flow

## Decision
No forms. Pure conversational onboarding across ~7 turns, under 5 minutes.
The LLM acts as an invested mentor from turn one.

## Conversation arc

```
Phase 1 — Goal & Timeline (2 turns)
  "What are you working towards? Goal and timeline."
  Captured: goal, deadline → writes Layer 1 immediately

Phase 2 — Current State (3 turns)
  "Where are you right now? College, working, between jobs?"
  "How far into DSA are you? Any topics you feel solid on?"
  Captured: current level, strong/weak areas → seeds Skill Graph

Phase 3 — File Upload (1 turn)
  "Drop your resume and LeetCode export if you have them."
  resume.pdf  → extract → parse → enriches L1 + L2
  leetcode.csv → parse → updates skill graph signals
  (optional — onboarding works without uploads)

Phase 4 — Availability (1 turn)
  "How many hours a day can you realistically put in?"
  Captured: daily_availability → Layer 1
```

## What gets written at end of onboarding

```
MongoDB — Layer 1 (Core Profile)
  goal, deadline, level, availability

MongoDB — Layer 2 (Skill Graph)
  one node per topic:
  current_level (from conversation + resume + LeetCode)
  required_level (from Goal Knowledge Base)
  gap (calculated)

Vector DB — Layer 3
  first episodic entry:
  "Onboarding session. Goal is 20 LPA. Weak in graphs
   and DP. Has internship experience. 2hrs/day."
```

## Schema generation
The LLM generates the MongoDB skill graph schema at the end of
onboarding. No developer involvement per user. Different goals
produce different topic sets and fields.

## No resume / no exports
Onboarding still completes. Skill graph is seeded from conversation alone.
Gaps are less precise initially — the evaluation loop corrects them
over the first few sessions.

## Goal evolution during onboarding
If the user mentions multiple aspirations, the mentor clarifies and
locks in one primary goal. Only one active goal is allowed.
Goal can evolve later but re-onboarding is not triggered — just an update.
