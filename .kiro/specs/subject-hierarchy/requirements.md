# Requirements Document

## Introduction

This document captures the requirements for introducing **Subject** as an optional organizational parent above **Topic**. Today every Topic is a flat, independent conversation thread in the sidebar. This feature lets a user group related Topics under a named Subject (e.g. "DSA", "System Design") while keeping Topic creation, re-parenting, and the existing L1/L2/L3 memory model entirely unchanged. Subject is purely a UI/organizational layer — it introduces no new memory scope and no requirement to use it.

## Glossary

- **Subject**: A named, user-owned grouping of Topics (e.g. "DSA", "System Design"). Has no conversation content of its own.
- **Topic**: The existing persistent conversation thread (see `topic-conversations-compaction` spec). Gains an optional, mutable `subjectId` reference.
- **SubjectService**: The service responsible for Subject CRUD operations, listing, and re-parenting Topics.
- **Unassigned Topic**: A Topic whose `subjectId` is `null` — a fully valid, first-class state, not an error or a migration artifact.
- **Subject_Sidebar**: The evolved sidebar UI component that renders Subjects as expandable groups and Unassigned Topics as a flat trailing list.
- **Re-parenting**: The act of changing a Topic's `subjectId` after creation, including clearing it back to `null`.

## Requirements

### Requirement 1: Subject Creation

**User Story:** As a learner, I want to create named subjects so that I can group related topics under a common heading.

#### Acceptance Criteria

1. WHEN a user creates a subject with a title, THE SubjectService SHALL validate the title is between 1 and 100 characters after trimming whitespace and create a new subject with status "active"
2. IF a subject title fails validation, THEN THE SubjectService SHALL reject the operation and return an error indicating the title must be between 1 and 100 non-whitespace-only characters
3. WHEN a subject is created, THE SubjectService SHALL set `createdAt` and `lastActiveAt` to the creation time and `topicCount` to 0
4. THE SubjectService SHALL scope every subject to a single owning `userId`, matching the existing Topic ownership model
5. THE SubjectService SHALL NOT require a subject to exist before a Topic can be created

### Requirement 2: Topic-to-Subject Association

**User Story:** As a learner, I want to optionally assign a topic to a subject, either at creation or later, so that I am never forced to organize before I am ready to.

#### Acceptance Criteria

1. WHEN a topic is created without a `subjectId`, THE TopicService SHALL persist the topic with `subjectId` set to `null` and treat this as a valid, terminal state (not a placeholder awaiting migration)
2. WHEN a topic is created with a `subjectId`, THE TopicService SHALL validate that the referenced subject exists, belongs to the authenticated user, and has status "active" before persisting the association
3. IF a `subjectId` provided at topic creation does not resolve to a subject owned by the authenticated user, THEN THE TopicService SHALL reject the operation with an error indicating the subject was not found
4. WHEN a topic is successfully created with a `subjectId`, THE SubjectService SHALL increment that subject's `topicCount` and update its `lastActiveAt` to the topic's `createdAt`

### Requirement 3: Topic Re-parenting

**User Story:** As a learner, I want to move a topic to a different subject (or remove it from a subject entirely) after creation, so that I can reorganize as my learning evolves.

#### Acceptance Criteria

1. WHEN a user changes a topic's `subjectId` to a different active subject they own, THE TopicService SHALL update the topic's `subjectId`, decrement `topicCount` on the previous subject (if any), and increment `topicCount` on the new subject
2. WHEN a user clears a topic's `subjectId` to `null`, THE TopicService SHALL update the topic to Unassigned and decrement `topicCount` on the previous subject
3. THE TopicService SHALL treat `subjectId` as mutable for the lifetime of the topic, with no restriction on the number of re-parenting operations
4. WHEN a re-parenting operation succeeds, THE TopicService SHALL increment the topic's `version` field following the same optimistic concurrency pattern used for message appends
5. IF a concurrent write conflict occurs during re-parenting, THEN THE TopicService SHALL refetch the document and retry up to 3 times before returning a conflict error, matching existing Topic concurrency handling

### Requirement 4: Subject Listing and Navigation

**User Story:** As a learner, I want to see my subjects and their topics in the sidebar as an expandable tree, with unassigned topics visible separately, so that I can navigate my organized and unorganized topics alike.

#### Acceptance Criteria

1. WHEN the user opens the application, THE Subject_Sidebar SHALL display all active subjects ordered by `lastActiveAt` descending, each showing its title and `topicCount`
2. WHEN a user expands a subject, THE Subject_Sidebar SHALL fetch and display that subject's active topics ordered by `lastActiveAt` descending, using the same title/timestamp/preview presentation as the existing Topic_Sidebar
3. THE Subject_Sidebar SHALL display all of the user's Unassigned Topics (active, `subjectId` is `null`) in a trailing flat list below the subject groups, using the same presentation as topics within a subject
4. WHEN a topic is re-parented, THE Subject_Sidebar SHALL reflect the topic under its new subject (or in the Unassigned list) without requiring a full page reload
5. IF the user has no subjects and no unassigned topics, THEN THE Subject_Sidebar SHALL display an empty state prompting the user to start a new conversation, consistent with the existing Topic_Sidebar empty state

### Requirement 5: Subject Lifecycle Management

**User Story:** As a learner, I want to archive or rename a subject so that my sidebar stays organized as my learning priorities change.

#### Acceptance Criteria

1. WHEN a user renames a subject, THE SubjectService SHALL update the title subject to the same 1–100 character validation as creation
2. WHEN a user archives a subject, THE SubjectService SHALL set its status to "archived" and cascade `status: "archived"` to every Topic currently referencing it
3. WHEN a subject is archived, THE Subject_Sidebar SHALL exclude it and its topics from the default listing, consistent with existing Topic archive behavior
4. THE SubjectService SHALL NOT delete Topics or their message history when their parent Subject is archived
5. IF a status transition other than "active" to "archived" is attempted on a subject, THEN THE SubjectService SHALL reject the operation and return an error indicating the transition is not permitted

### Requirement 6: Memory Scoping Non-Interference

**User Story:** As a system operator, I want the introduction of Subject to have zero effect on the existing L1/L2/L3 memory model, so that skill tracking and episodic retrieval remain correct and unchanged.

#### Acceptance Criteria

1. THE System SHALL NOT introduce any new memory storage layer keyed by `subjectId`
2. THE ContextAssembler SHALL continue to key L1 retrieval by `userId` only, L2 retrieval by `(userId, topic)` only, and L3 retrieval by `userId` with topic-biased ranking, with no reference to `subjectId` in any query
3. THE CompactionService and SkillGraphService SHALL continue to operate identically regardless of whether a topic has a `subjectId` set
4. Grouping or ungrouping topics under a subject SHALL NOT trigger any read or write to `profiles_col`, `skill_graph_col`, `sessions_col`, or `embeddings_col`

### Requirement 7: Data Integrity

**User Story:** As a system operator, I want subject-topic relationships to remain consistent under concurrent access so that topic counts and groupings never drift from reality.

#### Acceptance Criteria

1. THE SubjectService SHALL ensure a subject's `topicCount` always equals the count of non-archived topics currently referencing it via `subjectId`
2. THE TopicService SHALL ensure every non-null `subjectId` on a topic resolves to an existing subject owned by the same `userId`
3. WHEN a subject is archived, THE System SHALL NOT permit new topics to be created with that subject's id, nor permit existing topics to be re-parented to it, until it is reactivated
4. THE System SHALL include the authenticated `userId` as a filter in every database query for subject operations, matching the existing Topic access-control model

### Requirement 8: Security and Access Control

**User Story:** As a learner, I want my subjects to be as private as my topics, so that no one else can view or modify my organizational structure.

#### Acceptance Criteria

1. WHEN an API request targets a subject that does not belong to the authenticated user, THE System SHALL return HTTP 403 without revealing whether the subject exists
2. IF a subject id in a request does not match any subject in the system, THEN THE System SHALL return HTTP 404
3. THE System SHALL return identical error responses for "subject not found" and "subject belongs to another user" scenarios to prevent user enumeration, consistent with existing Topic error handling

### Requirement 9: Backward Compatibility and Migration

**User Story:** As an existing user, I want my current topics to remain fully usable after this feature ships, without being forced into a default subject.

#### Acceptance Criteria

1. WHEN this feature is deployed, THE System SHALL treat every existing Topic's absent `subjectId` field as equivalent to `subjectId: null` (Unassigned) without requiring a data migration
2. THE System SHALL NOT auto-create a default "Uncategorized" or "General" subject for any user
3. Existing Topic API consumers that do not send a `subjectId` SHALL continue to function unchanged, with topics created as Unassigned
