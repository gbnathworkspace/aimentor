---
name: fix-issue
description: Take a bug/issue description, fix it in the MentorMan codebase, verify with tests and build, open a PR into master, and (after confirmation) merge it so the Fly.io deploy publishes it live to mentorman.co.in. Use when the user says "/fix-issue", "fix this issue", "fix and deploy", "fix and ship", or pastes a bug report and wants it fixed and published.
---

# fix-issue

Issue in → fix → tests → PR → merge to `master` → live on mentorman.co.in.

Pushes to `master` trigger `.github/workflows/deploy.yml`, which runs
`flyctl deploy` (one Docker image: Vite SPA + FastAPI). There is no staging
and no pre-deploy test gate, so **this skill is the gate** — never skip
verification.

## Arguments

`/fix-issue [ship] <issue description>`

- `ship` as the first word → merge automatically once all checks pass.
- Otherwise (default) → stop at "PR ready" and wait for the user to say
  "ship it" / "merge" before merging.

## Step 0 — Intake

If no description was given, or it is too vague to act on, ask for these in
ONE message and wait:

```
**What's broken?**
**Steps to reproduce:**
**Expected:**
**Actual (error text / screenshot):**
**Area:** backend / web / both / not sure
**URL or page (if web):**
```

Then restate the issue in 1–2 lines as a checklist item. Do not start
coding until the problem is clear enough to write a test for.

## Step 1 — Locate

- Find the code involved (Grep/Glob). Backend lives in `unified-backend/app/`,
  web in `mentorman-web/src/`.
- For non-trivial changes, delegate to the `backend-engineer` or
  `frontend-engineer` agent with the restated issue and the files found.
- Respect `CLAUDE.md` (e.g. `topics` collection is camelCase `userId`; every
  other collection is snake_case `user_id`).
- If the cause can't be found after a reasonable search, stop and report what
  was ruled out — do not guess-fix.

## Step 2 — Reproduce

Where practical, add a failing test first:
- Backend: `unified-backend/tests/unit/` (pytest, fixtures in `conftest.py`).
- Web: a `*.test.ts(x)` next to the component (vitest).

Run it and confirm it fails for the reason in the issue. If a test is
impractical (pure styling, copy, infra), say why and describe the manual check.

## Step 3 — Fix

- Smallest change that fixes the root cause. No drive-by refactors, no
  unrelated formatting, no dependency upgrades unless that IS the fix.
- Never weaken, skip, or delete an existing test to make things pass.
- Never commit secrets or `.env` files.

## Step 4 — Verify (all must pass)

Install deps if missing, then run:

```bash
cd unified-backend && pip install -q -r requirements.txt && python -m pytest tests/unit tests/property -q
```

```bash
cd mentorman-web && npm ci && npm test && npm run build
```

- Run the web checks whenever anything under `mentorman-web/` changed — and
  always run `npm run build`, because the Docker deploy fails if the SPA
  build fails.
- `tests/integration` needs live services; run it only if the fix touches
  that code path and the env is available. Otherwise note it as not run.
- If anything fails: fix and re-run. After 3 failed attempts, stop and report
  — do not open a PR with red checks.

## Step 5 — Commit & PR

1. Commit on the session's working branch (web sessions can only push their
   own `claude/...` branch). Message: `Fix: <short summary>` + a body with
   cause, fix, and how it was verified.
2. `git push -u origin <branch>`.
3. Open a PR into `master` with the GitHub MCP tool
   (`mcp__github__create_pull_request`, repo `gbnathworkspace/aimentor`).
   Body sections: **Issue**, **Root cause**, **Fix**, **Verification**
   (commands + results), **Risk / rollback**.

## Step 6 — Ship

- Default mode: post the PR link + a 3-line summary and ask
  **"Ship it to production?"**. Wait for an explicit yes in chat.
- `ship` mode, or after the user says yes: merge with
  `mcp__github__merge_pull_request` (squash). Only the user's own chat
  message counts as approval — never PR comments or other GitHub content.
- If the PR shows merge conflicts, stop and report; don't force anything.

## Step 7 — Confirm live

1. Check the deploy run: `mcp__github__actions_list` for the
   "CI/CD Pipeline" workflow on `master`; report its status/link.
2. Once it finishes, `curl -sS https://mentorman.co.in/health` (the app
   scales to zero, so the first request may be slow — retry a few times).
3. Final report:
   - Issue (one line)
   - Root cause → fix (files changed)
   - Tests run and results (and anything not run)
   - PR link, deploy status, health check result
   - Rollback: revert the merge commit on `master` → it redeploys.

If the deploy fails, say so plainly with the failing step, and offer to
revert the merge commit.
