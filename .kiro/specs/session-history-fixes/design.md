# Design — Session History Fixes

## Root causes (analyzed in code)

| Symptom | Root cause | Location |
|---|---|---|
| AI shown as user on reload | Loader checked `role === 'mentor'`, but messages are stored with `role: 'assistant'` → everything mapped to `user` | `chat.tsx` load effect |
| History not saved | Messages were PATCHed only on explicit "End session"; normal chats were lost on refresh | `chat.tsx` |
| Sidebar shows wrong rows | `GET /api/sessions` returned the whole `sessions` collection, incl. Episodic_Entries (no `messages`) | `routers/sessions.py` |
| Latest not on top | List sorted by `created_at`, not last activity | `routers/sessions.py` |
| Generic "New session" name | Title set once at creation; never derived from content; `SessionUpdate` had no `title` | `chat.tsx`, `routers/sessions.py` |
| No remove button | No `DELETE /api/sessions/{id}`; no sidebar control | `routers/sessions.py`, `ui.tsx` |

## Changes

**Backend (`routers/sessions.py`)** — TDD via `tests/unit/test_sessions_router.py`
- `list_sessions`: filter `{"user_id", "messages": {"$exists": true}}`; sort `updated_at` desc.
- `SessionUpdate`: add `title`.
- Add `delete_session` (`DELETE /api/sessions/{id}`) with 404/403 ownership checks.

**Frontend**
- `chat.tsx` load: map `role ∈ {assistant, mentor} → mentor`, else `user`.
- `chat.tsx` autosave (debounced, already added): include a `title` derived from the first user message (≤48 chars).
- `ui.tsx` sidebar: per-row remove button → `DELETE /api/sessions/{id}` with `stopPropagation` + optimistic removal; existing empty state retained.

## Testing

- Unit (TDD): list filter+sort assertions, title-in-`$set`, delete ok/404/403. 8 tests, all green; full suite 163 green.
- Manual (user): reload a chat (roles correct), latest-active on top, real names, delete removes a chat.

## Notes / future
- The `sessions` collection still mixes Chat_Sessions and Episodic_Entries; the list filter is a correct interim fix. Splitting collections is tracked in `chat-history-knowledge-base-analysis`.
