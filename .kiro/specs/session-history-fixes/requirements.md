# Requirements — Session History Fixes

## Introduction

After the React migration, the chat-history / sidebar experience had several production defects: reopened chats showed AI replies as the user's own messages, the sidebar listed non-chat documents, sessions weren't ordered by recent activity, chats had no meaningful name, and there was no way to delete a chat. This spec defines correct, production-ready behavior for persisting, listing, naming, ordering, viewing, and deleting chat sessions. Backend changes are covered by unit tests (TDD).

## Glossary

- **Chat_Session**: A live conversation document in the `sessions` collection with a `messages` array.
- **Episodic_Entry**: A post-session summary document (with an `embedding`, no `messages`) that also lives in `sessions`.
- **Sidebar_List**: The session list rendered in the left sidebar.

## Requirements

### Requirement 1: Correct message attribution on reload
**User Story:** As a user, when I reopen a past chat, I want my messages and the mentor's messages shown on the correct sides.
#### Acceptance Criteria
1. WHEN a stored session is loaded, THE UI SHALL render messages with `role` `assistant` (or `mentor`) as mentor messages and `user` as user messages.
2. THE UI SHALL NOT render mentor messages as user messages or vice versa.

### Requirement 2: History persists without "End session"
**User Story:** As a user, I want my conversation saved automatically so refreshing doesn't lose it.
#### Acceptance Criteria
1. THE chat SHALL persist messages to the backend after each exchange (not only on explicit end).
2. WHEN a user reloads and reopens a session, THE stored messages SHALL be present.

### Requirement 3: Sidebar lists only real chats, most-recent first
**User Story:** As a user, I want the sidebar to show my chats with the latest on top.
#### Acceptance Criteria
1. THE session list SHALL include only Chat_Sessions (documents with a `messages` array) and SHALL exclude Episodic_Entries.
2. THE session list SHALL be ordered by last activity (`updated_at`) descending.
3. WHEN there are no chats, THE sidebar SHALL show an empty state.

### Requirement 4: Meaningful chat name
**User Story:** As a user, I want each chat named so I can tell them apart.
#### Acceptance Criteria
1. THE Chat_Session title SHALL be derived from the first user message (truncated) when available.
2. THE backend SHALL allow updating a session `title`.
3. THE Sidebar_List SHALL display the session title.

### Requirement 5: Delete a chat
**User Story:** As a user, I want to remove a chat I no longer need.
#### Acceptance Criteria
1. THE backend SHALL expose `DELETE /api/sessions/{id}`.
2. IF the session does not exist, THEN it SHALL return 404; IF it is not owned by the user, THEN 403.
3. THE sidebar SHALL show a remove control per chat that deletes it and updates the list without opening it.

### Requirement 6: Tests and integrity
#### Acceptance Criteria
1. THE sessions router SHALL have unit tests for list filtering/sorting, title update, and delete (incl. 404/403).
2. THE full backend suite SHALL remain green; the SPA SHALL build clean.
