---
name: devsession
description: Session start/end ritual for solo MentorMan dev work — enforces WIP cap (max 2 active specs), one-task-per-commit discipline, NEXT: line handoff, and a parking lot for stray ideas. Use when the user says "start session", "what should I work on", "end session", "wrap up", "devsession".
---

# devsession

Two modes: `start` and `end`. Infer the mode from the user's phrasing if not
given explicitly ("what should I work on" = start, "wrap up" / "done for now"
= end). Everything below reuses existing Kiro spec files — no new tooling,
no database, no external tracker.

## Mode: start

1. List directories directly under `.kiro/specs/`, excluding `archived/` and
   `parked/`. These are the "active" specs.
2. If more than 2 active specs exist, stop and tell the user which ones —
   ask which 1-2 stay active. Move the rest into `.kiro/specs/parked/`
   (create it if missing) with `git mv`. Do not proceed to step 3 until the
   count is <= 2.
3. For each active spec, read `tasks.md`. Look for a `NEXT:` line near the
   top of the first in-progress (unchecked) task. Print it verbatim — this
   is the exact resume point from last session, don't re-derive it.
4. If a spec's `design.md` has a `## Parking lot` section, print its items
   so the user can decide whether to pull one into tasks.md now (as its own
   task) or leave it parked.
5. Tell the user: pick exactly ONE task from tasks.md before writing any
   code. Remind them the goal is one commit per task, not one commit per
   session — a long session should still produce several small commits, not
   one large one.

## Mode: end

1. Ask the user (or infer from the conversation) what was just finished and
   what the very next concrete step is.
2. Edit that spec's `tasks.md`: add or update a `NEXT: <one line>` directly
   above the in-progress task item. Overwrite any stale `NEXT:` line already
   there.
3. Ask if anything came up mid-session that isn't part of the current task
   (a new idea, a "we should also..."). If yes, append it as a bullet under
   `## Parking lot` in that spec's `design.md` (create the heading if it
   doesn't exist). Do NOT fold it into the current task or tasks.md scope.
4. Run `git status` and `git diff --stat`. If the diff spans clearly
   unrelated concerns (e.g. touches files for two different features), flag
   it and suggest splitting into separate commits before the user commits —
   don't let a multi-concern diff land as one commit.
5. Remind the user to commit before closing the session, even if the task
   isn't finished (WIP commits are fine) — an uncommitted pile is what turns
   into a cram-everything-in binge next time.
