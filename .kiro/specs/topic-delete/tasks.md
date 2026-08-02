# Implementation Plan: topic-delete

## Overview

Adds permanent per-topic deletion across backend and frontend.
The backend gets a `delete_topic` service method with cascade cleanup and a `DELETE /api/topic/{topic_id}` router endpoint.
The frontend gets a `DeleteTopicDialog` confirmation component, a hover-reveal delete button in both `TopicSidebar` and `ArchivedTopics`, and the CSS that controls its visibility.
A `trash` icon is added to the shared icons component before any UI work begins.

## Tasks

- [x] 1. Add `trash` icon to the icons component
  - Add `'trash'` to the `IconName` union type in `mentorman-web/src/components/mentorman/icons.tsx`
  - Add the corresponding SVG path to the `I` record — a simple bin/trash outline (e.g. `<g><path d="M3 5h10M8 8v4M6 8v4M10 8v4" /><path d="M5 5V3.5h6V5" /><rect x="3" y="5" width="10" height="8" rx="1" /></g>`)
  - Verify `Icon name="trash"` renders without TypeScript error
  - _Requirements: 1.1, 1.2_

- [x] 2. Implement `TopicService.delete_topic` with cascade
  - [x] 2.1 Add `delete_topic` method to `unified-backend/app/services/topic_service.py`
    - Import `compaction_events_col` and `immediate_contexts_col` from `app.config.database` (they are already present in `database.py`)
    - Ownership check: `find_one({topicId, userId})` → raise `HTTPException(404)` if not found, identical to `get_topic` pattern
    - Cascade step 1: `await compaction_events_col().delete_many({"topicId": topic_id, "userId": user_id})` — wrapped in try/except, log warning on failure
    - Cascade step 2: `await immediate_contexts_col().delete_many({"session_id": topic_id})` — wrapped in try/except, log warning on failure
    - Final step: `await topics_col().delete_one({"topicId": topic_id, "userId": user_id})` — topic doc deleted **last** so cascade failures remain retryable
    - Do **not** touch `skill_graph_col`, `subtopic_lists_col`, `weight_nudges_col`, or `uploads/`
    - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2_

  - [ ]* 2.2 Write unit tests for `delete_topic` cascade and ordering (`TestDeleteTopic` class in `unified-backend/tests/unit/test_topics_router.py`)
    - `test_delete_topic_success` — 200 `{"ok": true}`, service called with `("topic-abc", "user-123")`
    - `test_delete_non_owner_returns_404` — service raises `HTTPException(404)`, response is 404
    - `test_delete_not_found_returns_404` — same as above (enumeration prevention)
    - `test_delete_archived_topic_success` — service called with `status="archived"` topic, returns 200 (no status-gating)
    - `test_delete_no_auth_returns_401` — request without auth headers → 401
    - `test_delete_cascade_order` — service-level test mocking all three collection callables; asserts `delete_many` on `compaction_events` and `delete_many` on `immediate_contexts` are called **before** `delete_one` on `topics`
    - `test_delete_skill_graph_survives` — mock verifies `skill_graph_col` is never called during `delete_topic`
    - Follow the `_setup_settings` / `_sample_topic` / `AsyncMock` patterns already in `test_topics_router.py`
    - _Requirements: 3.2, 3.3, 4.4, 8.1, 8.2, 8.3, 8.4_

- [x] 3. Add `DELETE /api/topic/{topic_id}` endpoint
  - Add the route to `unified-backend/app/routers/topics.py` immediately after the `archive_topic` route
  - Signature: `@router.delete("/topic/{topic_id}")` with `user_id: str = Depends(require_auth)`
  - Delegate to `await _topic_service.delete_topic(topic_id, user_id)`
  - Return `{"ok": True}` — consistent with `memory.py:127`
  - No additional status check (`active` and `archived` both accepted)
  - _Requirements: 3.1, 3.3, 3.4, 3.5_

- [ ] 4. Checkpoint — run backend tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create `DeleteTopicDialog` component
  - Create new file `mentorman-web/src/components/mentorman/DeleteTopicDialog.tsx`
  - Mirror the structure of `SkipConfirmationDialog.tsx` exactly: same `dialogRef`/`cancelBtnRef` refs, same `useEffect` focus-cancel-on-open, same Tab trap `handleKeyDown`, same Escape handler
  - Props interface:
    ```typescript
    interface DeleteTopicDialogProps {
      open: boolean;
      topicTitle: string;
      onConfirm: () => void;
      onCancel: () => void;
      loading?: boolean;
      error?: string | null;
    }
    ```
  - Static content: title `"Delete topic?"`, body `"'<topicTitle>' and all its messages will be permanently deleted. This cannot be undone."`, Cancel button (focused on open), Delete button (`btn btn-danger` or the destructive variant used in the design system — use `--danger` colour token)
  - Cancel button: `disabled={loading}`, triggers `onCancel`
  - Delete button: `disabled={loading}`, `aria-busy={loading}`, label `loading ? 'Deleting…' : 'Delete'`
  - Inline error: render `<div className="skip-dialog-error" role="alert">{error}</div>` when `error` is truthy
  - Overlay click calls `onCancel` only when `!loading` — same as `SkipConfirmationDialog`
  - Reuse CSS class namespace: `skip-dialog-overlay / skip-dialog / skip-dialog-title / skip-dialog-desc / skip-dialog-actions` — no new CSS classes needed for the dialog itself
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 6. Add delete state and handler to `TopicSidebar`
  - [~] 6.1 Add delete state variables and `onClearActiveTopic` prop to `TopicSidebar`
    - Add optional prop `onClearActiveTopic?: () => void` to `TopicSidebarProps` interface
    - Add three state variables at the top of the component:
      ```typescript
      const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
      const [deletingId, setDeletingId] = useState<string | null>(null);
      const [deleteError, setDeleteError] = useState<string | null>(null);
      ```
    - _Requirements: 6.2, 6.5_

  - [~] 6.2 Add delete button to `renderRow` in `TopicSidebar`
    - Inside `renderRow`, after the existing subject-tag button block, add the delete button guarded by `{!collapsed && (...)}`:
      ```typescript
      {!collapsed && (
        <button
          className="session-delete-btn"
          title="Delete topic"
          aria-label={`Delete topic ${topic.title}`}
          onClick={(e) => {
            e.stopPropagation();
            setDeleteError(null);
            setPendingDeleteId(topic.topicId);
          }}
          disabled={deletingId === topic.topicId}
        >
          <Icon name="trash" size={12} />
        </button>
      )}
      ```
    - `e.stopPropagation()` prevents the row `onClick` from firing (same pattern as the subject-edit button)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [~] 6.3 Add `handleDeleteConfirm` handler and wire `DeleteTopicDialog` in `TopicSidebar`
    - Add the `handleDeleteConfirm` async function:
      - Guard: `if (!pendingDeleteId || deletingId) return`
      - Set `deletingId(pendingDeleteId)`, clear `deleteError`
      - `fetch(\`/api/topic/${topicId}\`, { method: 'DELETE' })`
      - On 404: close dialog, call `fetchTopics()` — treat as already gone
      - On non-ok (not 404): `throw new Error('Delete failed')`
      - On success (ok): `setTopics(prev => prev.filter(t => t.topicId !== topicId))`, close dialog, call `onClearActiveTopic?.()` only if `selectedTopicId === topicId`
      - `catch`: `setDeleteError('Could not delete topic. Please try again.')`
      - `finally`: `setDeletingId(null)`
    - Import `DeleteTopicDialog` at the top of the file
    - Render `<DeleteTopicDialog>` outside the `.sidebar` div (as a sibling portal-like overlay), controlled by `pendingDeleteId`:
      ```typescript
      {pendingDeleteId && (
        <DeleteTopicDialog
          open={!!pendingDeleteId}
          topicTitle={topics.find(t => t.topicId === pendingDeleteId)?.title ?? ''}
          onConfirm={handleDeleteConfirm}
          onCancel={() => { setPendingDeleteId(null); setDeleteError(null); }}
          loading={deletingId === pendingDeleteId}
          error={deleteError}
        />
      )}
      ```
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 6.1, 6.2, 6.3, 6.5, 7.1, 7.2, 7.3_

- [ ] 7. Add delete support to `ArchivedTopics`
  - [~] 7.1 Add delete state variables and delete button to `ArchivedTopics`
    - Add the same three state variables (`pendingDeleteId`, `deletingId`, `deleteError`) at the top of `ArchivedTopics`
    - In the `topics.map(...)` render block, add the delete button inside each `.session` div (same JSX as `TopicSidebar` step 6.2, guarded by `{!collapsed && ...}`)
    - _Requirements: 1.5_

  - [~] 7.2 Add `handleDeleteConfirm` handler and wire `DeleteTopicDialog` in `ArchivedTopics`
    - Add `handleDeleteConfirm` following the same logic as `TopicSidebar` — the key differences:
      - No `selectedTopicId` check and no `onClearActiveTopic` call (archived topics are never the active chat)
      - On 404: close dialog, call `fetchArchivedTopics()` to refresh
      - On success: `setTopics(prev => prev.filter(t => t.topicId !== topicId))`, close dialog
    - Import `DeleteTopicDialog` and render it outside the `.sidebar` div, same pattern as `TopicSidebar`
    - _Requirements: 1.5, 2.1, 2.3, 6.1, 7.1, 7.2_

- [~] 8. Wire `onClearActiveTopic` callback in the parent layout
  - Locate the component in `mentorman-web/src` that owns `activeTopic` / `setActiveTopic` state (confirmed at `chat.tsx:454-455`) and renders `TopicSidebar`
  - Pass `onClearActiveTopic={() => setActiveTopic(null)}` (or equivalent setter call) as a prop to `TopicSidebar`
  - Verify `TopicSidebar` now receives the callback and that deleting the active topic returns the chat panel to its empty/new-topic state
  - _Requirements: 6.2, 6.3_

- [~] 9. Add CSS for `.session-delete-btn` visibility
  - Add the following rules to `mentorman-web/src/globals.css`, in the sidebar section immediately after the existing `.session-tag-btn` block:
    ```css
    /* Per-row "delete topic" affordance — hidden by default, revealed on row hover/focus */
    .session-delete-btn {
      position: absolute; right: 32px; bottom: 6px;
      display: flex; align-items: center; justify-content: center;
      width: 22px; height: 22px; border-radius: var(--r-sm);
      border: 1px solid transparent; background: transparent;
      color: var(--muted); cursor: pointer; opacity: 0;
      pointer-events: none;
      transition: opacity .12s, color .12s, background .12s;
    }
    .session:hover .session-delete-btn,
    .session:focus-within .session-delete-btn {
      opacity: 1;
      pointer-events: auto;
    }
    .session-delete-btn:hover {
      color: var(--danger);
      background: var(--danger-weak);
      border-color: var(--danger-line);
    }
    ```
  - The `right: 32px` positions the delete button to the left of the existing `session-tag-btn` (which sits at `right: 6px`)
  - The `pointer-events: none` default ensures the button is not accidentally keyboard-reachable when invisible — the JSX `!collapsed` guard removes it from the DOM entirely when collapsed
  - _Requirements: 1.1, 1.3, 1.4_

- [~] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- No property-based tests: the design has no "Correctness Properties" section (deletion is a straightforward imperative flow, not a universal algebraic property)
- Task 1 (trash icon) must be done before any UI tasks — TypeScript will fail to compile until `'trash'` is in the `IconName` union
- Task 3 (router endpoint) depends on Task 2.1 (service method) — the router delegates to `_topic_service.delete_topic`
- Task 8 (wire callback in layout) can be done in parallel with Tasks 6 and 7 since it touches a different file
- The `btn-danger` class does not appear in `globals.css`; use the existing `--danger` CSS variable directly on the confirm button, or add a minimal `.btn-danger` rule alongside the other `.btn-*` variants if preferred
- No database migrations, no new collections, no new npm/Python packages required

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "5"] },
    { "id": 2, "tasks": ["2.2", "3"] },
    { "id": 3, "tasks": ["6.1", "7.1"] },
    { "id": 4, "tasks": ["6.2", "7.2"] },
    { "id": 5, "tasks": ["6.3", "8", "9"] }
  ]
}
```
