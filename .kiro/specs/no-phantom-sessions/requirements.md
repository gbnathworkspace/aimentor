# Requirements — No Phantom Sessions & Upload Status

## Introduction

Two defects in the chat lifecycle: (1) a backend session was created automatically every time the chat opened (during the greeting), flooding the sidebar with empty "phantom" sessions the user never started; (2) file uploads stored and worked, but the status UI showed **Timeout** because the backend reported a non-terminal status the client kept polling. This spec defines correct lazy session creation and correct upload-status termination.

## Glossary
- **Phantom_Session**: a backend session created without a deliberate user action (just by opening/greeting).
- **Lazy_Creation**: creating the backend session only on the user's first real action (send a message or upload a file).
- **Terminal_Status**: an upload status the client treats as final and stops polling on (`done`, `partial`, `failed`).

## Requirements

### Requirement 1: No session is created without a user action
**User Story:** As a user, I don't want new chats appearing that I never started.
#### Acceptance Criteria
1. WHEN the chat opens and only the greeting is shown, THE app SHALL NOT create a backend session.
2. THE app SHALL create the session lazily on the user's first action (first sent message or first uploaded file).
3. THE app SHALL create AT MOST ONE session per conversation (guarded against duplicate/in-flight creation).
4. WHEN the page is reloaded mid-conversation, THE app SHALL resume the SAME backend session (id persisted in the draft), not create a new one.

### Requirement 2: Sidebar reflects only real chats
#### Acceptance Criteria
1. WHEN a session is created lazily, THE sidebar SHALL refresh to show it.
2. THE app SHALL NOT leave greeting-only sessions in the list.

### Requirement 3: Upload status terminates correctly
**User Story:** As a user, when my file finishes processing, I want it to show "ready", not "Timeout".
#### Acceptance Criteria
1. WHEN extraction completes, THE backend SHALL report a Terminal_Status (`done`) with `extractionReady: true`.
2. THE client SHALL stop polling and show the ready state once a Terminal_Status is received.
3. IF extraction yields no text or errors, THEN THE backend SHALL report `failed`.

### Requirement 4: Integrity
#### Acceptance Criteria
1. THE SPA SHALL build clean; THE backend suite SHALL remain green.
2. Upload-first (selecting a file before typing) SHALL still work — the pending file is submitted once the lazily-created session exists.
