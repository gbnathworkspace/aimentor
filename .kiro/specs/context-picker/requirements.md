# Requirements Document

## Introduction

The Settings > Memory screen currently renders `learning_context` (the L1
enum — `job_interview`, `high_stakes_exam`, `competitive_test`,
`self_directed`, `other`) as a plain HTML `<select>` dropdown
(`screens.tsx:688-696`), saved via its own "Save" button.

This is visually inconsistent with `Situation` (the free-text
`learning_context_detail.label`), which was just converted from an inline
input into a `SituationsModal` — a click-to-open dialog with a styled list
of options. The ask is to bring `Context` to the same visual treatment.

## Open question to resolve before design

The user's request referenced a visual reference ("make context like this")
that did not come through with the message. Two readings are plausible —
pick one before design.md:

1. **Cosmetic only.** Replace the `<select>` element with a button that
   opens a small dialog listing the 5 fixed `LearningContext` values
   (styled like `SituationsModal`'s row list — dot indicator, click to
   select) — no search box, no add box, since the option set is fixed and
   small. Closest re-use of `.sw-dialog`/`.sit-row` styles already shipped.
2. **Structural parity with Situations.** Same dialog chrome, but also
   surfaces `learning_context_detail.structured` (the per-context key/value
   facts — `seniority_level`, `target_comp`, etc. — currently written by
   nothing, see `profile.py:83-88`) inside the same picker, so choosing a
   context and filling its structured detail happens in one place instead
   of two.

Reading 1 is the smaller, more literal match to "make Context like
Situations" (i.e. the dialog *shape*, not scope creep into the unrelated
structured-fields gap). Reading 2 pulls in the earlier-discussed
`ALLOWED_STRUCTURED_KEYS` gap and is a materially bigger change. Default to
1 unless told otherwise.

## Requirements

### Requirement 1 — Trigger

**User Story:** As a user, I want the same click-to-open interaction for
Context as I have for Situation, so the two related fields feel like one
system instead of two different UI patterns.

#### Acceptance Criteria

1. WHEN the user is on Settings > Memory THEN the "Context" row SHALL
   render a button showing the current context's display label (e.g.
   "Job interview"), not a native `<select>`.
2. WHEN the user clicks the Context button THEN the system SHALL open a
   dialog matching `SituationsModal`'s chrome (`.sw-overlay`/`.sw-dialog`/
   `.sw-head`, close button, Escape-to-close).

### Requirement 2 — Selecting a context

**User Story:** As a user, I want to pick my context from a list, so
selecting is a single click instead of a dropdown-then-Save round trip.

#### Acceptance Criteria

1. THE dialog SHALL list all 5 `LearningContext` values with a dot
   indicator matching `.sit-dot`/`.sit-dot-active` — filled = current.
2. WHEN the user clicks a non-active option THEN the system SHALL save
   `learning_context` immediately (same immediate-save behavior as
   `SituationsModal`, no separate Save button) via `PUT /api/profile`,
   preserving the existing `learning_context_detail` (label, situations,
   structured) unchanged — matching the fix already made in
   `saveSituations` that stopped the old Save button from wiping
   `structured`/`situations` on every context change.
3. IF the save fails THEN the system SHALL revert the optimistic selection
   and show an inline error, matching `SituationsModal`'s `commit()`
   pattern.

### Requirement 3 — No search/add for this field

**User Story:** As the developer, I don't want UI affordances that don't
make sense for a fixed 5-value enum.

#### Acceptance Criteria

1. THE dialog SHALL NOT include a search box or an "add new" input —
   unlike Situations, the option set is fixed and not user-extensible.

### Requirement 4 — Scope boundary

**User Story:** As the user, I want this change contained to the
presentation of `learning_context`, not a rework of related fields.

#### Acceptance Criteria

1. THE change SHALL NOT touch `learning_context_detail.structured` or the
   `ALLOWED_STRUCTURED_KEYS` gap (tracked separately, see Open Question
   above, reading 2) unless reading 2 is explicitly chosen.
2. THE change SHALL NOT touch the `Situation` row/modal already shipped.

## Out of scope

- A generic reusable "picker modal" component — this is a second instance
  of the same pattern, not yet a proven-enough case to abstract (rule of
  three).
- Structured per-context fields (seniority/comp/etc.) — separate from this
  spec, see [[feedback_l1_flexible_input]] memory on keeping structured
  extraction behind free text rather than new form fields.
