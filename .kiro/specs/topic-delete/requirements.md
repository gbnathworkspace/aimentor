# Requirements Document

## Introduction

Topics are the top-level unit of conversation (`unified-backend/app/services/topic_service.py`,
sidebar at `mentorman-web/src/components/mentorman/TopicSidebar.tsx`). Today a topic
can be created, listed, renamed, and archived — but never removed. A mistyped topic,
a throwaway test thread, or a conversation the user doesn't want kept stays in the
sidebar forever.

This feature adds deletion: a per-topic action in the sidebar, a `DELETE` endpoint,
and cleanup of the rows in other collections that reference the deleted topic.

**Blocking observation:** the sidebar has *no per-topic action affordance at all*
today. Each topic row is a bare `<div onClick={selectTopic}>` (`TopicSidebar.tsx:220-250`).
`POST /topic/{id}/archive` exists in the backend and is wired to nothing in the
frontend — `grep archive mentorman-web/src` finds only the "View Archived" list link.
So this feature has to introduce the row-action mechanism, and archive gets a
trigger for free once it exists.

## What a topic actually owns

Established by tracing every collection that stores a topic reference:

| Store | Key | Delete with the topic? |
|---|---|---|
| `topics` | `topicId` | **Yes** — messages are embedded in the doc, so they go with it |
| `compaction_events` | `topicId` (`compaction_service.py:652`) | **Yes** — audit rows for a thread that no longer exists |
| `weight_nudges` | `topic_id` (`topics.py:239-251`) | **Decision needed** — see Requirement 5 |
| `immediate_contexts` | `session_id` (`session_upload.py:58`) | **Yes** — the chat passes `sessionId={topicId}` (`chat.tsx:559`), so these rows are topic-scoped and have no TTL |
| `skill_graph` | `(user_id, topic-name)` (`skill_graph_repo.py:41`) | **No** — keyed by subject name, not `topicId`. Learning already absorbed from the thread survives it |
| `subtopic_lists` | `topic` title, unique, no `user_id` | **No** — a global cross-user cache |
| `sessions` (L3 episodic) | `session_id` | **No linkage today** — the topic chat path never writes it (`topic_chat_service.py` has no `session_id` reference); legacy session flow only |
| `uploads/` on disk | `user_id/job_id` | **No** — already TTL-swept by `file_cleanup.py:43`, not addressable by topic |

## Open decision to resolve before design

**Hard delete or soft delete?**

`TopicStatus` is `z.enum(['active', 'archived'])` (`lib/topics/types.ts:15`). Adding
a third `'deleted'` status would be a smaller diff than a cascade, and recoverable.

1. **Hard delete** (recommended). Single user, and archive already covers
   "keep it but hide it" — a soft-delete tier on top of archive is two flavours of
   hidden with no user-visible difference. Follows the existing precedent in
   `memory.py:103-127` and `sessions.py:370-382`, both `delete_one`.
2. **Soft delete.** `status: 'deleted'`, filtered out of both list queries.
   Recoverable, no cascade needed — but every list/aggregate query in the codebase
   now has to remember to exclude it, and the data never actually goes away.

Pick one in design.md. The requirements below are written against option 1; under
option 2, Requirements 4 and 5 collapse into a status flip.

## Requirements

### Requirement 1 — Delete entry point in the sidebar

**User Story:** As a user, I want to delete a topic from the topic list, so that
threads I don't want don't accumulate in my sidebar.

#### Acceptance Criteria

1. WHEN the user hovers or focuses a topic row in the sidebar THEN the system SHALL
   reveal a per-row action control that does not trigger topic selection when
   activated.
2. WHEN the user activates that control THEN the system SHALL offer a Delete action.
3. THE action control SHALL be reachable by keyboard, not hover only — the row is
   currently a `div` with no `role` or `tabIndex`, so this requires making the row
   or the control focusable.
4. WHEN the sidebar is collapsed (`.sidebar.collapsed`) THEN the system SHALL NOT
   render an orphaned action control with no visible row context.
5. THE same action control SHALL be available in the archived list
   (`ArchivedTopics.tsx`), since an archived topic is the most likely delete target.

### Requirement 2 — Confirmation before destruction

**User Story:** As a user, I want to confirm before a topic disappears, so that a
misclick doesn't destroy a conversation I spent an hour on.

#### Acceptance Criteria

1. WHEN the user chooses Delete THEN the system SHALL require an explicit
   confirmation before issuing any request.
2. THE confirmation SHALL name the topic being deleted by title, so the user can
   see they picked the intended row.
3. THE confirmation SHALL state that deletion is permanent and that the thread's
   messages go with it.
4. IF the user dismisses or cancels the confirmation THEN the system SHALL make no
   request and leave the topic untouched.
5. THE confirmation SHALL reuse the existing dialog component
   (`SkipConfirmationDialog.tsx` / `ListModal.tsx`) rather than a native
   `window.confirm` or a third dialog implementation.

### Requirement 3 — Delete endpoint

**User Story:** As the frontend, I need one endpoint that removes a topic and
everything scoped to it, so that cleanup can't drift out of sync with deletion.

#### Acceptance Criteria

1. THE system SHALL expose `DELETE /api/topic/{topic_id}`, authenticated via
   `require_auth`, matching the router conventions in `topics.py`.
2. WHEN the topic does not exist OR is owned by a different user THEN the system
   SHALL return an identical 404 for both cases, per the enumeration-prevention
   rule already applied across `topics.py` (Req 15.5).
3. THE endpoint SHALL accept topics in both `active` and `archived` status —
   unlike `archive_topic`, which rejects non-active topics with 409.
4. WHEN deletion succeeds THEN the system SHALL return a success body consistent
   with the existing delete routes (`{"ok": true}` in `memory.py:127`).
5. WHEN the same topic is deleted twice THEN the second call SHALL return 404, not
   a 500 — deletion is not required to be idempotent, but must fail cleanly.

### Requirement 4 — Cascade cleanup

**User Story:** As the operator of a free-tier M0 cluster, I don't want rows for
deleted topics accumulating in collections nobody queries anymore.

#### Acceptance Criteria

1. WHEN a topic is deleted THEN the system SHALL delete its `topics` document,
   which removes the embedded `messages` array with it.
2. WHEN a topic is deleted THEN the system SHALL delete all `compaction_events`
   rows matching `{topicId, userId}`.
3. WHEN a topic is deleted THEN the system SHALL delete all `immediate_contexts`
   rows matching `{session_id: topic_id}` — the chat uploads under the topic id
   (`chat.tsx:559`), so these are otherwise permanently orphaned with no TTL.
4. THE system SHALL NOT delete `skill_graph` entries — they are keyed by subject
   name, are shared across topics, and represent learning that outlives the thread.
5. THE system SHALL NOT delete `subtopic_lists` entries — that collection is a
   global cross-user cache keyed by topic title with no `user_id` field
   (`database.py:99`).
6. THE system SHALL NOT delete files under `uploads/` — they are keyed by
   `user_id/job_id`, not reachable from a topic id, and already TTL-swept by
   `file_cleanup.py`.
7. IF a cascade delete fails after the topic document is removed THEN the system
   SHALL log the failure with the topic id rather than leaving the caller with a
   partial-success response of unclear meaning (exact ordering and failure
   semantics — topic-doc-last vs. best-effort — decided in design.md).

### Requirement 5 — Weight nudges retention

**User Story:** As the person tuning the subtopic-weighting model, I want to keep
the signal about where users disagreed with computed weights, even after the topic
that produced it is gone.

#### Acceptance Criteria

1. THE design SHALL make an explicit call on `weight_nudges` rows for a deleted
   topic, and record the reasoning.
2. IF nudges are retained THEN the system SHALL retain them on the stated grounds
   that they are model-tuning telemetry, not user content — the router docstring
   already argues this is "the only place that signal gets kept" (`topics.py:230-233`).
3. IF nudges are deleted THEN the system SHALL delete rows matching
   `{user_id, topic_id}` and the design SHALL note the telemetry loss.
4. WHICHEVER is chosen, a user deleting a topic SHALL NOT be able to observe the
   retained rows through any existing endpoint — no route reads `weight_nudges` today.

### Requirement 6 — UI state after deletion

**User Story:** As a user, I want the app to behave sensibly right after I delete
the topic I was reading, so that I'm not staring at a dead thread.

#### Acceptance Criteria

1. WHEN deletion succeeds THEN the system SHALL remove the topic from the sidebar
   list without a full-page reload, using the existing `refreshKey`/`topicsVersion`
   refresh path (`app.tsx:27`, `TopicSidebar.tsx:108-110`).
2. WHEN the deleted topic is the currently selected topic THEN the system SHALL
   clear `activeTopic` so the chat panel returns to its topic-creation state
   (`chat.tsx:454-455`), rather than fetching a topic that now 404s.
3. WHEN the deleted topic is not the selected one THEN the system SHALL leave the
   current selection and chat view untouched.
4. WHEN the last topic in the list is deleted THEN the sidebar SHALL show its
   existing empty state ("No topics yet…"), not an empty scroll area.
5. WHEN deletion is in flight THEN the system SHALL prevent a second delete
   submission for the same topic.

### Requirement 7 — Failure handling

**User Story:** As a user, I want to know when a delete didn't work, so that I
don't assume a topic is gone when it isn't.

#### Acceptance Criteria

1. IF the delete request fails THEN the system SHALL leave the topic in the sidebar
   and surface an error to the user — no optimistic removal that silently reappears
   on next fetch.
2. IF the request returns 404 THEN the system SHALL treat the topic as already
   gone and refresh the list rather than showing a hard error.
3. THE error surface SHALL match the sidebar's existing failure treatment
   (inline message with a retry affordance, per `TopicSidebar.tsx:179-198`).

### Requirement 8 — Verification

**User Story:** As the developer, I want the cascade covered by a test, because a
silently-skipped collection is invisible until the cluster fills up.

#### Acceptance Criteria

1. THE system SHALL have a backend test asserting that after a delete, no rows for
   that `topic_id` remain in `topics`, `compaction_events`, or `immediate_contexts`.
2. THE system SHALL have a backend test asserting that a delete by a non-owner
   returns 404 and leaves the topic intact.
3. THE system SHALL have a test asserting `skill_graph` rows survive the delete.
4. Tests SHALL follow the existing layout under `unified-backend/tests/`.

## Out of scope

- Bulk / multi-select delete. Single-row delete only.
- Undo, trash, or a restore window. Archive already serves "hide but keep".
- Deleting individual messages within a topic.
- Wiring archive to the new row-action control — this spec only requires that the
  control exist; whether archive gets an entry there is a follow-up.
- Any change to `file_cleanup.py` or the `uploads/` TTL sweep.
- Account-level "delete all my data" — `DELETE /api/profile` already exists
  separately and is not touched here.
