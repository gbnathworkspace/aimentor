# Memory

Project memory lives in `.claude/memory/` and is committed to the repo, so it
survives across machines and cloud sessions (whose containers are thrown away).
The index is `.claude/memory/MEMORY.md`, imported from `CLAUDE.md`.

## Recall — Before Responding

Check memory when the message involves past decisions, preferences, system
knowledge, or prior work. Skip when the topic is already fully in context.

To recall: scan the MEMORY.md index descriptions for relevance and load only
the matching memory files. Don't load everything — be selective.

## Remember — After Responding

Run this decision tree after every substantive response:

1. **Does this exchange contain a user directive, reasoning conclusion, or
   durable fact?** If no to all, stop.
2. **Does an overlapping memory exist?** If yes, update it. If it contradicts,
   replace it. If no overlap, create a new file.
3. **Is it worth storing?** Multi-source synthesis or user-specific context
   that can't be recovered by search? Yes, save. Single-query public fact? Skip.

## Memory File Format

Save each memory as its own kebab-case file in `.claude/memory/`
(e.g. `feedback-no-trailing-summaries.md`):

```markdown
---
name: descriptive-name
description: one-line summary for relevance matching
type: user | feedback | project | reference
---

Content here. For feedback/project types, include:
**Why:** reason behind it
**How to apply:** when this matters
```

## What NOT to Save

- Code patterns derivable from reading the codebase
- Git history (use git log)
- Debugging solutions (the fix is in the code)
- Ephemeral task details for the current session only
- Anything already in `CLAUDE.md` or other project docs
- Secrets, API keys, tokens, or connection strings — this directory is committed

## Index Maintenance

After creating or updating a memory file, add or update its one-line entry in
`.claude/memory/MEMORY.md` (keep it under 200 lines). Commit memory changes
with the rest of the work so they aren't lost when the session ends.
