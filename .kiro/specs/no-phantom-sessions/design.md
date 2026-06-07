# Design — No Phantom Sessions & Upload Status

## Root causes (verified in code)

| Symptom | Root cause |
|---|---|
| New sessions appear without user action | The **auto-greet** effect in `chat.tsx` did `POST /api/sessions` on every fresh `'new'` mount (even on initial load with `activeSession='new'`), so just opening/refreshing the chat created an empty session. |
| Duplicate session on reload | `backendSessionId` lived only in component state and was lost on refresh; the draft restored messages but not the id, so the next action created a new session. |
| Upload shows "Timeout" though it worked | The upload endpoint reported `status: "ready"`, but the client's `TERMINAL_STATUSES` are `{done, partial, failed}`. `ready` is non-terminal, so the client kept polling until `MAX_POLL_COUNT` (30×2s) → **timeout**, despite extraction having succeeded. |

## Changes

**Frontend `chat.tsx`**
- Auto-greet: render the greeting only — **no session creation**.
- `ensureSession(firstUserText?)`: creates the session **once** (guarded by `backendSessionId` + an in-flight `creatingRef`), sets the id, derives the title from the first message, and calls `onSessionSaved()` to refresh the sidebar.
- `send()`: `const sid = backendSessionId || await ensureSession(text)`; uses `sid` for the mentor call. Autosave (existing) then persists messages.
- Upload-first: `handleFileSelected` calls `ensureSession()` if there's no session; a new effect submits the pending file once `backendSessionId` is set (the upload hook re-renders with the real id).
- Draft now stores `backendSessionId`; the load path restores it so a reload resumes the same session.

**Backend `routers/session_upload.py`**
- On successful extraction set job `status: "done"` (terminal) with `extraction_ready: true`; on empty/error set `failed`. The status endpoint returns `{status, extractionReady, summary}`.

## Why "done" works
The client first branch (`extractionReady && !readyEmitted`) emits the ready UI and message; then the terminal check (`TERMINAL_STATUSES.has('done')`) stops polling and finalizes — so the user sees "ready" and polling ends cleanly.

## Testing
- Backend suite green (163). (Upload uses BackgroundTasks + multipart; covered by the status-value change + manual verification.)
- SPA builds clean.
- Manual (user): open chat → no phantom session; send first message → exactly one session appears; reload mid-chat → same session continues; upload a PDF → shows ready (no timeout).

## Related / not in scope
- Invalid `VOYAGE_API_KEY` (seen in logs) disables L3 vector search (degrades gracefully). Tracked in `chat-history-knowledge-base-analysis`.
