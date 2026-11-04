---
name: fix-issue
description: Take a bug/issue description (or a GitHub issue number), label it by type, area and severity, fix it in the MentorMan codebase, verify with tests and build, open a PR into master, and (after confirmation) merge it so the Fly.io deploy publishes it live to mentorman.co.in. Use when the user says "/fix-issue", "fix this issue", "fix and deploy", "fix and ship", or pastes a bug report and wants it fixed and published.
---

# fix-issue

Issue in → fix → tests → PR → merge to `master` → live on mentorman.co.in.

Pushes to `master` trigger `.github/workflows/deploy.yml`, which runs
`flyctl deploy` (one Docker image: Vite SPA + FastAPI). There is no staging
and no pre-deploy test gate, so **this skill is the gate** — never skip
verification.

## Arguments

`/fix-issue [ship] <issue description>`

- `ship` as the first word → merge automatically once all checks pass
  (the issue/label confirmation in Step 0.5 still happens).
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

If the argument is an existing GitHub issue (`#12` or an issue URL), read it
with `mcp__github__issue_read` and use its title/body as the description.

## Step 0.5 — Label the issue

Classify the issue and pick exactly one label from each group:

| Group | Labels | How to choose |
|---|---|---|
| Type | `bug`, `ui`, `performance`, `security`, `enhancement` | What kind of problem it is. Wrong behaviour/crash = `bug`; visual/layout/copy = `ui`; slow = `performance`; auth/data exposure = `security`; "should also do X" = `enhancement` |
| Area | `area:backend`, `area:web`, `area:both`, `area:infra` | Where the fix will land (`unified-backend/`, `mentorman-web/`, both, or deploy/config). Revisit after Step 1 if the code says otherwise |
| Severity | `sev:critical`, `sev:high`, `sev:medium`, `sev:low` | critical = site down / data loss / security hole; high = core flow (login, chat, topics) broken for users; medium = feature broken with a workaround; low = cosmetic |

Always add `auto-fix` as well, so these issues are easy to filter.

### Confirm before going further (always — even in `ship` mode)

Show the user this and **stop until they reply**:

```
**Issue:** <1–2 line restatement>
**Labels:** bug · area:web · sev:high · auto-fix
**Why:** <one line on the type/area/severity choice>

Proceed with these labels? (yes / change labels / edit issue)
```

- **yes** → continue below.
- **change labels** or **edit issue** → apply their changes, show the block
  again, and wait for another yes.
- Anything else / no reply → do nothing further. Do not create or label an
  issue, and do not touch code, until the user has said yes.

Then, on `gbnathworkspace/aimentor`:
- **Existing issue given** → add the labels to it with `mcp__github__issue_write`
  (keep any labels already on it).
- **Issue only described in chat** → create a GitHub issue with
  `mcp__github__issue_write`: title = the 1-line restatement, body = the
  intake fields, labels = the confirmed labels. Note its number `#N` and
  share the link.

GitHub creates a label the first time it's used. If the area or severity
changes after Step 1, tell the user the new labels and update the issue.

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
   (commands + results), **Risk / rollback**. Put `Fixes #N` at the top of
   the body so merging closes the issue, and add the issue's labels to the PR.

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
   - Issue (one line), issue link `#N` and its labels
   - Root cause → fix (files changed)
   - Tests run and results (and anything not run)
   - PR link, deploy status, health check result
   - Rollback: revert the merge commit on `master` → it redeploys.

If the deploy fails, say so plainly with the failing step, and offer to
revert the merge commit.
