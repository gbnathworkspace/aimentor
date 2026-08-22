# How tasks get managed on this project

Solo dev, day job, real coding time happens in irregular evening/weekend
bursts separated by multi-day gaps (not a steady daily hour). These rules
exist to stop specs from sprawling and tasks from never closing. Anyone or
anything managing tasks here (human or agent) follows these:

1. **WIP cap: at most 2 active specs.** Everything else lives in
   `.kiro/specs/parked/`. A parked spec doesn't get touched until an active
   one is actually finished (moved to `.kiro/specs/archived/`).

2. **One task = one commit.** Never let unrelated concerns land in the same
   commit. If a task's description touches more than ~2 files, split it in
   `tasks.md` before starting.

3. **`NEXT:` line handoff.** The in-progress task in each active spec's
   `tasks.md` carries a `NEXT: <one line>` note above it, written at the end
   of the last session that touched it. Read this first — it's the exact
   resume point, don't re-derive it from scratch.

4. **Parking lot, not scope creep.** New ideas that surface mid-task or
   between sessions go under a `## Parking lot` heading in that spec's
   `design.md`, as their own future task — never folded into the task
   currently being built.

5. **Acceptance check is part of the task, not a follow-up.** Every task
   line item should read as "do X, verified by Y (a test/assert/repro
   step)" — not implementation now, testing later. Later doesn't happen.

An agent managing tasks here should: read this file first, then apply these
rules when advising on what to work on, when flagging WIP violations, when
asked to help split a task, or when triaging a parking-lot item back into an
active task.
