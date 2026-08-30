# Requirements Document

## Introduction

The L2 skill graph (`SkillNode`) currently represents a user's proficiency in a topic as one coarse label — `current_level` (`beginner`/`intermediate`/`advanced`/`expert`) — set by an LLM's subjective judgment call and treated as ground truth everywhere it's read (mode routing, the mentor prompt, subtopic weighting, the dashboard). This is inaccurate by construction: a user can be advanced on one subtopic and a total beginner on another within the same topic, and a single word can't represent that.

This feature replaces `current_level` (and the fields that only existed to support it or were never actually used) with a **persisted, per-subtopic mastery map** — `subtopic_mastery: dict[str, float]`, keyed by the topic's existing cached subtopic list (`get_subtopics()`), each value 0-100. The map is updated **incrementally**: any event that produces signal about specific subtopics (a diagnostic verdict mid-turn, or a compaction/session-end extraction) overwrites only the subtopics it has evidence for; every other subtopic keeps its last known value.

This is a deliberately simpler alternative to the more elaborate `skill-graph-v2` design (Elo updates, append-only observations, confidence scores, decay-on-read, prerequisite DAGs) that was previously proposed and never built — that design was rejected as more machinery than currently needed. `weak_areas`/`strong_areas`, currently stored as separate fields, become a derived view over the mastery map (a threshold split) instead of independently-tracked data.

## Glossary

- **SkillNode**: The L2 skill graph document per `(user_id, topic)`, defined in `app/models/skill.py`, persisted in the `skill_graph` collection.
- **Subtopic_Mastery_Map**: The new field on SkillNode — `dict[str, float]`, subtopic name → 0-100 mastery estimate. The sole per-topic skill signal going forward.
- **Canonical_Subtopic_List**: The cached, per-topic list of 6-9 subtopic names returned by `get_subtopics(topic)` (`app/services/subtopic_weights.py`), generated once via LLM decomposition and reused for every user.
- **Diagnostic_Verdict**: The mid-turn tool call (`record_diagnostic_verdict`) the mentor makes during `DIAGNOSTIC` sub-mode once it has enough signal to assess the user.
- **Compaction_Skill_Extraction**: The skill-update portion of the compaction/session-end LLM call (`_COMPACTION_TOOL_SCHEMA` in `compaction_service.py`) that also produces the session's narrative summary and taught-concepts list.
- **Assessed**: The existing `bool` field on SkillNode gating cold-start diagnostic routing (`mode_router.py` Rule 1). Unaffected by this feature.

## Requirements

### Requirement 1: SkillNode schema change

**User Story:** As the system, I want SkillNode to store per-subtopic mastery instead of one topic-level label, so that skill representation reflects reality instead of a coarse guess.

#### Acceptance Criteria

1. THE SkillNode model SHALL remove the fields `current_level`, `previous_level`, `signals`, and `prerequisites`.
2. THE SkillNode model SHALL add `subtopic_mastery: dict[str, float]` defaulting to an empty dict, where each value is constrained to the range 0-100.
3. THE SkillNode model SHALL retain `topic` and `assessed` unchanged.
4. THE system SHALL NOT persist `weak_areas` or `strong_areas` as independent stored fields going forward — any code path that previously wrote them SHALL instead write only to `subtopic_mastery`.
5. THE system SHALL NOT perform a migration of existing `skill_graph` documents — old documents may retain stale `current_level`/`previous_level`/`signals`/`prerequisites` keys in MongoDB (schemaless, inert) until a future write to that document naturally omits them.

### Requirement 2: Incremental merge semantics

**User Story:** As the system, I want mastery updates to touch only the subtopics an event has evidence for, so that a single observation doesn't overwrite everything else that's known about the topic.

#### Acceptance Criteria

1. WHEN a Diagnostic_Verdict or Compaction_Skill_Extraction produces a set of `(subtopic, mastery)` pairs for a topic, THE system SHALL overwrite only those specific keys in the topic's existing `subtopic_mastery` map.
2. THE system SHALL NOT modify any key in `subtopic_mastery` that a given update does not mention.
3. IF the topic's `SkillNode` does not yet exist, THEN THE system SHALL create it with `subtopic_mastery` containing only the subtopics the update provides values for (not pre-seeded with the full canonical list at zero).
4. THE system SHALL set `assessed = True` on any successful merge, matching current behavior for the fields it replaces.

### Requirement 3: Subtopic name validation

**User Story:** As the system, I want extracted subtopic names constrained to a known set, so that near-duplicate names don't fragment the mastery map over time.

#### Acceptance Criteria

1. WHEN a Diagnostic_Verdict or Compaction_Skill_Extraction proposes a mastery value for a subtopic name, THE system SHALL validate that name against the topic's Canonical_Subtopic_List (`get_subtopics(topic)`) before merging.
2. IF a proposed subtopic name does not case-insensitively match an entry in the Canonical_Subtopic_List, THEN THE system SHALL discard that single `(subtopic, mastery)` pair and proceed with the remaining valid pairs in the same update.
3. THE system SHALL normalize a validated subtopic name to its canonical casing/spelling from the Canonical_Subtopic_List before storing it as a key, so that lookups by that list elsewhere always hit.

### Requirement 4: Diagnostic verdict tool schema

**User Story:** As the mentor, I want to report per-subtopic mastery instead of one overall level when I've diagnosed a user, so my assessment reflects what I actually observed.

#### Acceptance Criteria

1. THE `record_diagnostic_verdict` tool schema SHALL remove the `new_level` property and its enum.
2. THE `record_diagnostic_verdict` tool schema SHALL add a `subtopic_updates` property: an array of objects, each with a `subtopic` (string) and `mastery` (number, 0-100), for only the subtopics the model gathered enough signal on this turn.
3. THE `record_diagnostic_verdict` tool schema SHALL require at least one entry in `subtopic_updates` (a verdict with zero updates carries no information and should not be called).
4. WHEN the model calls `record_diagnostic_verdict`, THE system SHALL validate each `subtopic_updates` entry per Requirement 3 and merge the surviving entries into `subtopic_mastery` per Requirement 2.
5. THE diagnostic mode's instruction text (`prompt_store.py`'s `_MODE_INSTRUCTIONS["diagnostic"]`) SHALL be updated to direct the model to assess specific subtopics rather than an overall level.

### Requirement 5: Compaction skill extraction schema

**User Story:** As the system, I want the session-end/periodic compaction extraction to also report per-subtopic mastery, so ongoing progress updates the same mastery map the diagnostic verdict writes to.

#### Acceptance Criteria

1. THE `_COMPACTION_TOOL_SCHEMA`'s `skill_updates` array items SHALL remove `new_level` and replace it with `subtopic_updates` (same shape as Requirement 4: array of `{subtopic, mastery}`).
2. THE `_COMPACTION_TOOL_SCHEMA`'s `skill_updates` array items SHALL remove `weak_areas` and `strong_areas` as separate properties.
3. `_validate_skill_updates()` SHALL validate `topic` (non-empty string) and `subtopic_updates` (non-empty array of valid `{subtopic, mastery}` pairs) instead of `new_level`/`weak_areas`/`strong_areas`.
4. IF an extracted `skill_updates` entry has an empty or entirely-invalid `subtopic_updates` array after validation, THEN THE system SHALL drop that entry from the batch rather than merging a no-op update.

### Requirement 6: Skill graph write path

**User Story:** As the system, I want one merge function that both the diagnostic verdict and compaction extraction paths call, so mastery updates are applied consistently regardless of source.

#### Acceptance Criteria

1. `skill_graph_repo.apply_update()` SHALL accept a topic and a list of validated `(subtopic, mastery)` pairs (replacing its current `SessionSkillUpdate`-shaped input built around `new_level`/`weak_areas`/`strong_areas`).
2. `skill_graph_repo.apply_update()` SHALL perform the merge described in Requirement 2 via a single MongoDB `update_one` with `upsert=True`, mirroring the current transactional shape.
3. `skill_graph_repo.apply_update()` SHALL continue to log the write (topic, user_id, and the subtopics touched) at the same log level as today, and SHALL continue to catch and log (not raise) any MongoDB failure, preserving the existing non-blocking behavior.
4. `SessionSkillUpdate` (`app/models/session.py`) SHALL be updated to carry `subtopic_updates` instead of `new_level`/`weak_areas`/`strong_areas`; the now-unused `SkillLevel` enum SHALL be removed if nothing else references it.

### Requirement 7: Mentor prompt content

**User Story:** As the mentor, I want to see per-subtopic mastery in my context instead of one level word, so I can calibrate teaching per-subtopic instead of for the whole topic uniformly.

#### Acceptance Criteria

1. `mentor_v1.md`'s `{{current_level}}` placeholder SHALL be replaced with a new placeholder rendering the topic's `subtopic_mastery` map as a readable breakdown (subtopic name + mastery value per line).
2. IF `subtopic_mastery` is empty (topic not yet assessed), THEN THE rendered block SHALL show a placeholder message equivalent to today's "Not assessed" text, not an empty section.
3. `prompt_store._build_context_variables()` SHALL read `subtopic_mastery` from the skill context dict and format it via a new helper function, following the existing pattern of `_format_taught_concepts`/`_format_style_notes`.

### Requirement 8: Mode router payload

**User Story:** As the system, I want to stop sending a field that no longer exists to the mode router, without changing its routing behavior.

#### Acceptance Criteria

1. `mode_router.route_user_turn()`'s Haiku payload SHALL remove the `current_level` line.
2. THE routing rules (Rules 2-6) SHALL NOT be modified — they do not branch on skill level today, so this removal SHALL NOT change any routing decision.

### Requirement 9: Subtopic weighting integration

**User Story:** As the system, I want subtopic proficiency estimation to stop depending on a level that no longer exists, and ideally to feed the same mastery map instead of producing a throwaway estimate.

#### Acceptance Criteria

1. `_score_proficiency_llm()` and `derive_subtopic_weights()` SHALL remove the `current_level` parameter and the anchoring logic in the LLM prompt that depended on it.
2. THE `POST /topic/{topic_id}/subtopic-weights` endpoint SHALL stop reading `current_level` from `skill_graph_col` to pass into `derive_subtopic_weights()`.
3. Writing `_score_proficiency_llm()`'s output into the persisted `subtopic_mastery` map (rather than only returning it in the API response) is OUT OF SCOPE for this pass — see Out of Scope.

### Requirement 10: Manual skill API

**User Story:** As an operator, I want the manual skill CRUD endpoint to reflect the new schema, so it doesn't accept or return fields that no longer exist.

#### Acceptance Criteria

1. `SkillUpdate` (`app/models/skill.py`) SHALL remove `current_level` and `signals`, and SHALL add an optional `subtopic_mastery` field for direct override.
2. `PUT /api/skills/{topic}` SHALL merge a provided `subtopic_mastery` payload the same way as Requirement 2 (touched keys only) rather than replacing the whole map.

## Out of Scope

- Any dashboard/frontend UI redesign (`Topic.level`, `Topic.levelUp`, and their rendering in `dashboard.tsx`) — the badge becomes stale/unused data until a follow-up pass designs its replacement.
- Confidence scores, decay-on-read, observation history, or any other mechanism from the rejected `skill-graph-v2` design.
- A real prerequisite graph — `prerequisites` is deleted outright, not replaced; a future prerequisite feature needs its own design.
- Migrating or backfilling existing `skill_graph` documents.
- Persisting `_score_proficiency_llm()`'s estimate into `subtopic_mastery` — it remains an ephemeral, request-scoped estimate on the `goal_intent` subtopic-weighting path only.
- Any change to `assessed`'s semantics or the cold-start routing rule that depends on it.
