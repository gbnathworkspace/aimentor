# Implementation Plan: Subject Hierarchy

## Overview

Add Subject as an optional, mutable organizational parent above Topic. Implement SubjectService, extend TopicService with subject association and re-parenting, and evolve the sidebar into an expandable Subject tree with a trailing Unassigned Topics list. No changes to CompactionService, ContextAssembler, SkillGraphService, or any L1/L2/L3 memory read/write path.

## Tasks

- [ ] 1. Set up data models, interfaces, and indexes
  - [ ] 1.1 Create Subject data model and Zod/Pydantic schemas
    - Create `Subject`, `SubjectListItem` interfaces/schemas matching the design document data models
    - Extend the existing `Topic` schema with `subjectId: string | null`
    - _Requirements: 1.1, 1.3, 2.1, 9.1_

  - [ ] 1.2 Create MongoDB `subjects` collection and indexes
    - Unique index on `subjectId`
    - Compound index on `{userId: 1, status: 1, lastActiveAt: -1}` (mirrors existing topics sidebar-listing index)
    - Add compound index on `{subjectId: 1, status: 1, lastActiveAt: -1}` to the existing `topics` collection for per-subject topic listing
    - _Requirements: 4.1, 4.2, 7.1_

- [ ] 2. Implement SubjectService
  - [ ] 2.1 Implement create, get, list, rename methods
    - `create_subject(user_id, title)` with 1–100 char trimmed validation (reuse existing Topic title validator)
    - `get_subject(subject_id, user_id)` with ownership check, identical 403/404 semantics to TopicService
    - `list_subjects(user_id)` returning active subjects ordered by `lastActiveAt` descending as `SubjectListItem` projections
    - `rename_subject(subject_id, user_id, title)`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 5.1, 8.1, 8.2, 8.3_

  - [ ] 2.2 Implement archive with cascade
    - `archive_subject(subject_id, user_id)`: set status to "archived", then bulk-update all topics with matching `subjectId` to `status: "archived"`
    - Enforce active→archived as the only permitted transition
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

  - [ ] 2.3 Implement topicCount/lastActiveAt bookkeeping hooks
    - `on_topic_attached(subject_id, topic_created_at)`: increment `topicCount`, bump `lastActiveAt`
    - `on_topic_detached(subject_id)`: decrement `topicCount`
    - Reject attach attempts against a non-active subject
    - _Requirements: 2.4, 3.1, 3.2, 7.1, 7.3_

  - [ ]* 2.4 Write property test for topicCount consistency (Property 2)
    - **Property 2: topicCount Consistency**
    - Generate random sequences of create/re-parent/archive operations → verify stored `topicCount` always equals a live count of non-archived topics referencing the subject
    - **Validates: Requirement 7.1**

- [ ] 3. Extend TopicService with subject association
  - [ ] 3.1 Extend `create_topic` to accept optional `subject_id`
    - If `subject_id` provided, validate via `SubjectService.get_subject` (ownership + active status) before persisting; reject with 404-equivalent error if invalid
    - If omitted, persist `subjectId: null` (Unassigned) — no SubjectService call
    - On success with a subject_id, call `SubjectService.on_topic_attached`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 9.2, 9.3_

  - [ ] 3.2 Implement `set_topic_subject` (re-parenting)
    - Validate the new subject (if not null) is active and owned by the caller
    - Persist the new `subjectId` with a `version` bump, reusing the existing optimistic-concurrency retry loop (up to 3 retries)
    - Call `on_topic_detached` on the previous subject (if any) and `on_topic_attached` on the new one (if any)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.3_

  - [ ]* 3.3 Write property test for orphaned-reference prevention (Property in design doc: "No Orphaned References")
    - Generate random operation sequences → verify every topic's non-null `subjectId` always resolves to a subject with the same `userId`
    - **Validates: Requirement 7.2**

  - [ ]* 3.4 Write property test for Unassigned as a terminal state (Property 3)
    - Verify a topic created or re-parented to `subjectId: null` supports the full existing message/compaction/skill-update flow identically to a subject-attached topic
    - **Validates: Requirements 2.1, 9.1**

- [ ] 4. Verify memory-scoping non-interference
  - [ ] 4.1 Run the existing `topic-conversations-compaction` test suite unmodified against topics with and without a `subjectId`
    - Confirm zero behavioral drift in `ContextAssembler`, `CompactionService`, and `SkillGraphService`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 4.2 Write property test for memory scoping non-interference (Property 4)
    - Assert the set of L1/L2/L3 records read/written is identical regardless of `subjectId` value or re-parenting history
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [ ] 5. API routes
  - [ ] 5.1 `POST /api/subjects`, `GET /api/subjects`, `PATCH /api/subjects/{id}` (rename/archive)
  - [ ] 5.2 `GET /api/subjects/{id}/topics` (projection: topicId, title, status, lastActiveAt, message preview — same shape as existing Topic_Sidebar projection)
  - [ ] 5.3 Extend `POST /api/topics` to accept optional `subjectId`
  - [ ] 5.4 `PATCH /api/topics/{id}/subject` for re-parenting
    - _Requirements: 1.1, 2.2, 3.1, 4.1, 4.2, 8.1, 8.2_

- [ ] 6. Frontend: Subject_Sidebar
  - [ ] 6.1 Fetch and render active subjects as collapsible groups, ordered by `lastActiveAt`, showing `topicCount`
    - _Requirements: 4.1_

  - [ ] 6.2 Lazy-load topics per subject on expand; cache client-side until invalidated by create/re-parent/archive within that subject
    - _Requirements: 4.2_

  - [ ] 6.3 Render a trailing "Unassigned Topics" flat list using the existing Topic row presentation
    - _Requirements: 4.3_

  - [ ] 6.4 Add a "Move to Subject" action per topic row (picker: active subjects + "Unassigned"), wired to `PATCH /api/topics/{id}/subject`
    - _Requirements: 3.1, 3.2, 4.4_

  - [ ] 6.5 Keep "New Topic" creation subject-free by default; no blocking subject-selection step
    - _Requirements: 1.5, 9.3_

  - [ ] 6.6 Empty state: no subjects and no unassigned topics
    - _Requirements: 4.5_

- [ ] 7. Backward compatibility check
  - [ ] 7.1 Confirm existing Topic documents without a `subjectId` field are read as `null` (Unassigned) with no migration script required
    - _Requirements: 9.1, 9.2, 9.3_
