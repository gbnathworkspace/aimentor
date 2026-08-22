# Student eval agent (idea, parked)

Status: idea only, not started. Parked on creation — do not pull into active
WIP until an active slot is free and this has been through the normal
requirements/design/tasks flow.

## Origin

Surfaced 2026-08-22 in conversation, not tied to any existing active spec.

## Concept

An eval harness where an LLM plays a "naive student" persona — a college
student who has never used the app, doesn't know its features, and has a
concrete learning goal (e.g. "understand recursion for my CS assignment").
The persona talks to MentorMan through its real chat interface, unassisted
by a human. A separate judge pass then grades the transcript to answer:
how well does MentorMan teach/guide a totally new user to a solution on
its own?

## Components

1. **Student agent** — LLM call with a persona system prompt:
   - No knowledge of the app's UI/features; asks naive questions; may
     misuse the app (pastes homework verbatim, gets sidetracked, expresses
     confusion/frustration).
   - Has a concrete task goal plus a "knowledge state" that should visibly
     improve turn over turn if MentorMan is working.
   - Runs in a loop against MentorMan's real chat API for N turns, or
     until it self-reports understanding or gives up.

2. **Transcript logger** — captures every turn (student message, MentorMan
   response, any tool/skill triggered) as structured data.

3. **Judge / evaluation panel** — LLM grader(s) score the transcript on a
   rubric:
   - Did the student reach a correct solution without being handed the
     answer outright?
   - Turns-to-resolution (efficiency).
   - Did MentorMan detect confusion and adapt?
   - Did it use the app's actual features (skill graph, topic context)
     rather than answering like a generic chatbot?
   - Frustration/dropout signal — did the student "give up" mid-conversation?

4. **Output** — a scorecard per run plus the raw transcript, for manual
   spot-checking of failures.

## Scope note

Planned as a standalone offline script (student-agent + judge), not wired
into the product. UI/screen work for this is intentionally deferred to a
future session per the user.

## Next steps when unparked

- Write requirements.md and design.md properly (this file is just the
  captured idea).
- Break into tasks.md following the one-task-per-commit rule.
- Only promote to active once an active spec slot is free (WIP cap = 2).
