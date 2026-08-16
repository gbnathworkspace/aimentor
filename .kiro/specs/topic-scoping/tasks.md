# Implementation Plan: topic-scoping

## Overview

Adds `classify_relevance` + `l1_scope` filtering to L1 memory injection, and
gates `subtopic_weights.py` behind a new `subtopic_generator.py` human-review
graph. Both features write only to the existing `topics` document — no new
collections. `langgraph` is added as a dependency before any generator code is
written. The two known cache/leakage conflicts in `design.md` ("Design Risk 1
& 2") are resolved by construction in Task 8 — not left as follow-up cleanup.

## Tasks

- [ ] 1. Add `langgraph` to `requirements.txt`
  - Pin a version compatible with the installed `langchain-anthropic>=1.5.5`
  - Verify `pip install -r requirements.txt` succeeds and `from langgraph.graph
    import StateGraph` imports cleanly
  - _Requirements: 6.1_

- [ ] 2. Implement `classify_relevance`
  - [ ] 2.1 Create `app/services/classify_relevance.py`
    - Define `RelevanceJudgment(BaseModel)` with `situation`, `relevant`,
      `reason` fields
    - Define `async def classify_relevance(topic: str, subject: str | None,
      situations: list[str], contexts: list[str]) -> list[RelevanceJudgment]`
    - Prompt instruction: judge topical connection only, ignore
      urgency/casualness phrasing (the load-bearing line from the Notion doc)
    - Topic signal = `topic` + `subject` when subject is present (Decision B)
    - `situations` and `contexts` judged in one call, one judgment per entry,
      order preserved (Decision C)
    - Use `ChatAnthropic` (`claude-haiku-4-5-20251001`) +
      `.with_structured_output()` per the confirmed stack
    - Raise on failure — do not catch and return a partial/empty list; callers
      decide the fallback
    - Return `[]` immediately (no LLM call) when both `situations` and
      `contexts` are empty
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 2.2 Write `tests/unit/test_classify_relevance.py`
    - Hand-labeled eval cases across categories: clearly relevant, clearly
      irrelevant, the React/backend-interview failure case, urgency/casualness
      confound pair, adjacent-but-distinct domain, ambiguous/hard case,
      multi-topic situation
      — see `.kiro/specs/topic-scoping/requirements.md` Requirement 1.4 for
      the full category table
    - Assert per-category pass rate, not one aggregate number
    - _Requirements: 1.4_

- [ ] 3. Checkpoint — run `test_classify_relevance.py`, confirm category pass
  rates are acceptable before building on top of it. Ask the user if any
  category is below its threshold.

- [ ] 4. Wire `l1_scope` into `TopicService.create_topic()`
  - Fetch the user's `profiles_col` document inside `create_topic()`
  - Call `classify_relevance(title, subject, situations, contexts)`
  - On success: build `l1Scope` (drop `reason`, keep `situation` + `relevant`
    — Decision J) and `profileStamp = sha256(json.dumps({"situations":
    situations, "contexts": contexts}, sort_keys=True))` (Decision F)
  - On failure (any exception): set `l1Scope: None`, `profileStamp: None`, log
    a warning, still complete topic creation
  - Add `subtopicGen: None` to every new topic doc
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 5. Wire staleness recompute into `TopicService.get_topic()`
  - After the existing ownership-checked fetch, compute `current_stamp` from
    the user's live profile
  - If `current_stamp != topic.profileStamp` (covers `None` too): call
    `classify_relevance` again, update `l1Scope` + `profileStamp` on the
    document, return the updated doc
  - If `classify_relevance` fails on this path: log a warning, leave the
    stored `l1Scope`/`profileStamp` untouched, still return 200
  - If the match: skip the LLM call entirely (Property 2)
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ]* 5.1 Write/extend `tests/unit/test_topic_service.py`
  - `create_topic` success and failure paths (Task 4)
  - `get_topic` reuse-on-match vs. recompute-on-mismatch (Property 2)
  - `get_topic` recompute-failure leaves prior `l1Scope` intact
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

- [ ] 6. Add `topic_id` to `MentorRequest` and thread it through `mentor_chat()`
  - Add `topic_id: str = Field(..., alias="topicId")` to `MentorRequest`
    (`app/models/chat.py`) — keep the existing `topic: str` field, still used
    for the by-title `skill_graph` lookup
  - In `mentor_chat()` (`app/routers/mentor.py`), fetch the topic doc via
    `topics_col().find_one({"topicId": body.topic_id, "userId": user_id})`
    before calling `context_assembler.assemble(...)`
  - Return 404 if the topic doesn't exist or isn't owned by the caller,
    matching `get_topic()`'s enumeration-prevention convention
  - **Frontend**: update the mentor-chat request builder to send `topicId`
    alongside `topic` (find the call site — likely `chat.tsx` or
    `mentorman-api.ts` — grep for the existing `POST /api/mentor` fetch)
  - _Requirements: 4.4_

- [ ] 7. Wire `l1_scope` through context assembly and prompt formatting
  - [ ] 7.1 `context_assembler.assemble()` gains a `topic_doc: dict | None`
    parameter, passes `topic_doc.get("l1Scope")` through to
    `get_system_prompt` / `_format_learning_context`
  - [ ] 7.2 `_format_learning_context(profile, l1_scope)` — when `l1_scope` is
    not `None`, filter `contexts`/`situations` to entries marked
    `relevant: true`; an entry present in the profile but absent from
    `l1_scope` is treated as excluded, not included
  - [ ] 7.3 When `l1_scope is None` (pre-existing topic, or either failure
    path from Tasks 4/5): fall back to today's unfiltered formatting exactly
    — no behavior change for that case
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2_

- [ ]* 7.4 Update `tests/unit/test_prompt_store.py`
  - `l1_scope=None` reproduces today's output byte-for-byte
  - Populated `l1_scope` filters correctly (relevant kept, irrelevant dropped)
  - Entry in `situations` but missing from `l1_scope` is excluded
  - _Requirements: 4.1, 4.2, 4.3, 5.1_

- [ ] 8. Checkpoint — run backend tests, confirm Tasks 1–7 pass together before
  starting the subtopic-generator work (which depends on `l1Scope` existing).

- [ ] 9. Resolve Design Risk 1 & 2 before writing `subtopic_generator.py`
  - Confirm (by reading `subtopic_weights.py` again at implementation time,
    not assuming this doc is still accurate) that `subtopic_lists_col` remains
    untouched by anything this feature adds — the generator's approved output
    must never be written there (global, user-agnostic cache — see
    `design.md` "Design Risk 1")
  - Leave `get_subtopics()` / `_decompose_via_llm()` in place but unreferenced
    from the new gated path — do not delete them as part of this feature
    (`design.md` "Design Risk 2")
  - This task has no code change by itself — it's a guard-rail checkpoint so
    Task 11 doesn't accidentally reintroduce the leak
  - _Requirements: (Design Risk 1, 2 — not tied to a numbered requirement,
    tied to Decision H/I)_

- [ ] 10. Implement `subtopic_generator.py` (agent logic)
  - [ ] 10.1 Define `SubtopicGenState` (TypedDict) per `design.md`
  - [ ] 10.2 `classify_relevance` node — reuse `topic.l1Scope` if already set
    on the topic doc; otherwise call `classify_relevance` fresh and persist it
    to the topic doc via the same path as Task 4/5 (single source of truth —
    no second, divergent `l1Scope` write path)
  - [ ] 10.3 `generate_subtopics` node — Haiku call producing 6-9 subtopics,
    informed by the relevant-only `l1_scope` entries
  - [ ] 10.4 `human_review` node — `langgraph` `interrupt()`, surfaces
    `generated` for edit/approval
  - [ ] 10.5 `finalize` node — writes `subtopicGen: {status: "done", approved,
    updatedAt}` to `topics_col`. **Does NOT write to `subtopic_lists_col`**
    (Design Risk 1 — verified by Task 9)
  - _Requirements: (SubtopicGeneratorAgent section of requirements.md /
    Notion doc)_

- [ ] 11. Add `/agents/subtopic-generator/{start,resume}` endpoints
  - `POST start` — body `{topicId}`; loads topic, runs graph through
    `human_review`, persists `subtopicGen: {status: "awaiting_review", ...}`,
    returns the generated list
  - `POST resume` — body `{topicId, approved: list[str]}`; loads
    `topics.subtopicGen`, applies the edit, runs `finalize`
  - Both use `require_auth` + the same `{topicId, userId}` ownership check as
    every other topic endpoint; identical 404 for not-found/not-owned
  - _Requirements: (endpoints section of requirements.md)_

- [ ] 12. Gate `get_subtopic_weights()` on `subtopicGen.status == "done"`
  - Before calling `derive_subtopic_weights`, check
    `topic.subtopicGen?.status == "done"`; if not, raise `HTTPException(409,
    ...)` pointing at `/agents/subtopic-generator/start`
  - Replace the `get_subtopics(topic["title"])` call with
    `topic.subtopicGen.approved` — this is the call-site swap that makes
    Design Risk 1's resolution real, not just documented
  - _Requirements: Decision H (requirements.md)_

- [ ]* 12.1 Write `tests/unit/test_subtopic_generator.py`
  - Graph reuses existing `l1Scope` vs. computes fresh (Task 10.2)
  - `get_subtopic_weights` → 409 when `subtopicGen` is `None` or not `"done"`
    (Property 3)
  - `get_subtopic_weights` → 200, uses `subtopicGen.approved`, when `"done"`
  - `subtopic_lists_col` mock asserted never called from `finalize` (Property 4)
  - _Requirements: Decision H, Design Risk 1 (Property 3, Property 4 in
    design.md)_

- [ ] 13. Final checkpoint — full backend test suite green, `l1_scope`
  eval-suite category pass rates re-checked once integrated (not just in
  isolation from Task 3), frontend typecheck clean after Task 6's client change.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
  delivery, but 2.2 (the classifier eval suite) should not actually be
  skipped — it's the only thing that validates the feature's core correctness
  claim, per the Evals page in the Notion doc.
- Task 9 exists purely to force a design-risk re-check at implementation time,
  since `subtopic_weights.py` may have changed between this doc being written
  and Task 10 starting.
- No database migrations: `l1Scope: null`, `profileStamp: null`,
  `subtopicGen: null` are the correct "not yet computed" state for every
  topic that predates this feature — no backfill script needed (Requirement 5).
- `structured` key seen in some `learning_context_detail` write paths
  (`memory_editor.py`, `screens.tsx`) is unrelated to this feature — do not
  touch it.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3"] },
    { "id": 3, "tasks": ["4", "6"] },
    { "id": 4, "tasks": ["5", "5.1"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3", "7.4"] },
    { "id": 6, "tasks": ["8"] },
    { "id": 7, "tasks": ["9"] },
    { "id": 8, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5"] },
    { "id": 9, "tasks": ["11", "12"] },
    { "id": 10, "tasks": ["12.1"] },
    { "id": 11, "tasks": ["13"] }
  ]
}
```
