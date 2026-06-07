# Implementation Plan — Session History Fixes

Backend is test-first (TDD); frontend is manually verified.

## Tasks

- [x] 1. Backend: sessions router (TDD)
  - [x] 1.1 Add `tests/unit/test_sessions_router.py` covering list filter+sort, title update, delete (ok/404/403)
    - _Requirements: 6.1_
  - [x] 1.2 `list_sessions`: filter to `messages` exists; sort `updated_at` desc
    - _Requirements: 3.1, 3.2_
  - [x] 1.3 Add `title` to `SessionUpdate`
    - _Requirements: 4.2_
  - [x] 1.4 Add `DELETE /api/sessions/{id}` with 404/403 ownership checks
    - _Requirements: 5.1, 5.2_

- [x] 2. Frontend: chat history
  - [x] 2.1 Fix message role mapping on load (assistant/mentor → mentor)
    - _Requirements: 1.1, 1.2_
  - [x] 2.2 Autosave conversation after each exchange (debounced)
    - _Requirements: 2.1, 2.2_
  - [x] 2.3 Derive + send a title from the first user message
    - _Requirements: 4.1, 4.3_

- [x] 3. Frontend: sidebar delete
  - [x] 3.1 Per-row remove button → `DELETE` + optimistic update (stopPropagation)
    - _Requirements: 5.3_

- [x] 4. Verify
  - [x] Backend suite green (163); SPA builds clean; DELETE route live (401 without auth); fresh build served
    - _Requirements: 6.2_
