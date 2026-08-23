# Implementation Plan: Topic Scoping (l1_scope filtering)

## Overview

Adds `classify_relevance` + a lazily-computed, stamp-cached `l1_scope` on
the topic document, so `prompt_store.py` injects only the L1
situations/contexts relevant to the topic being discussed instead of
flattening all of them into every mentor turn. All logic lives in one new
module (`app/services/l1_scope.py`); `TopicService.get_topic()` gets the
lazy-compute hook; `context_assembler.assemble()` and
`prompt_store._format_learning_context()` thread the result through to the
prompt. No schema migration, no new dependency, no new collection.

## Tasks

- [x] 1. Create `app/services/l1_scope.py`
  - [x] 1.1 Add `extract_situations_and_contexts(profile: dict) -> tuple[list[str], list[str]]`
    - Move the contexts/situations/label-fold logic out of
      `prompt_store.py::_format_learning_context` verbatim — same fallback to
      `profile["learning_context"]` when `contexts` is empty, same
      label-inserted-if-not-already-present rule for `situations`
    - _Requirements: 4.1_

  - [x] 1.2 Add `compute_profile_stamp(situations: list[str], contexts: list[str]) -> str`
    - `hashlib.sha256` of `json.dumps({"situations": ..., "contexts": ...}, sort_keys=True)`
    - _Requirements: 2.1_

  - [x] 1.3 Add `classify_relevance(topic: str, situations: list[str], contexts: list[str]) -> list[dict]`
    - Pydantic schema: `_Judgment {relevant: bool, reason: str}` (no text
      field — see design.md's Component 1 note on why text is never
      requested from the model) and `_RelevanceJudgments
      {situation_judgments: list[_Judgment], context_judgments: list[_Judgment]}`
    - `ChatAnthropic(model="claude-haiku-4-5-20251001",
      api_key=get_settings().ANTHROPIC_API_KEY).with_structured_output(_RelevanceJudgments)`
    - Prompt: numbered `situations` and numbered `contexts` lists, instructs
      the model to judge topical connection only and explicitly ignore
      urgency/casualness of phrasing (Requirement 1.3's load-bearing line)
    - Returns `[]` immediately, no LLM call, when both input lists are empty
    - Raise `ValueError` if `len(result.situation_judgments) != len(situations)`
      or `len(result.context_judgments) != len(contexts)` — do not zip
      mismatched lengths
    - Build the return value by zipping `situations`/`contexts` (the real
      input text) against the judgments by position — the model's output
      never supplies the `situation` text
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.4 Write unit tests in `tests/unit/test_l1_scope.py`
    - `classify_relevance` returns `[]` without an LLM call when both lists
      are empty
    - `classify_relevance`'s output `situation` text matches the input list
      by position even when the mocked LLM's own content would suggest
      otherwise (proves text is never taken from the model)
    - `classify_relevance` raises `ValueError` on a judgment-count mismatch
      from the mocked LLM
    - `extract_situations_and_contexts` — folds `label` into `situations`
      only when absent; falls back to `profile["learning_context"]` when
      `contexts` is empty; regression-matches
      `prompt_store._format_learning_context`'s pre-change extraction
      behavior on the same fixtures
    - `compute_profile_stamp` — same output for identical input, different
      output when either list's contents change
    - _Requirements: 1.1-1.5, 2.1_

- [x] 2. Wire lazy compute into `TopicService.get_topic()`
  - [x] 2.1 Add `profiles_col` import to `unified-backend/app/services/topic_service.py`
    - Import from `app.config.database`, alongside the existing
      `compaction_events_col, immediate_contexts_col, topics_col` import
    - _Requirements: 3.1_

  - [x] 2.2 Add `_ensure_l1_scope(self, topic: dict, user_id: str) -> dict` to `TopicService`
    - Fetch profile via `profiles_col().find_one({"user_id": user_id}, {"_id": 0})`;
      return `topic` unchanged immediately if no profile exists
    - Compute `situations, contexts = extract_situations_and_contexts(profile)`
      then `current_stamp = compute_profile_stamp(situations, contexts)`
    - Cache hit: `topic.get("profileStamp") == current_stamp and "l1_scope" in topic`
      → return `topic` unchanged, no LLM call
    - Cache miss: call `classify_relevance(topic["title"], situations, contexts)`
      inside try/except; on success, `update_one({"topicId", "userId"},
      {"$set": {"l1_scope": ..., "profileStamp": current_stamp}})` and
      reflect both fields on the returned `topic` dict
    - On exception: `logger.exception(...)` with `topic_id` + `user_id`,
      return `topic` unchanged — no partial `$set`, no `profileStamp` write
      (Requirement 5.3 — a failed attempt must not look fresh)
    - _Requirements: 3.1, 3.2, 3.4, 5.1, 5.3_

  - [x] 2.3 Call `_ensure_l1_scope` from `get_topic()`
    - After the existing `find_one` + 404 check, `return await
      self._ensure_l1_scope(topic, user_id)` instead of returning `topic`
      directly
    - This is the single change point — it's what makes both `GET
      /topic/{topic_id}` and `TopicChatService.handle_message()`'s pre-turn
      fetch (which calls `self._topic_service.get_topic(...)` at
      `topic_chat_service.py:198`) pick up the lazy compute with no other
      call-site changes
    - _Requirements: 3.1_

  - [x]* 2.4 Write unit tests for `_ensure_l1_scope` / `get_topic`
    - Cache hit (matching `profileStamp`): `classify_relevance` not called
      (mock assertion), topic returned as fetched
    - Cache miss, fields absent: `classify_relevance` called once, topic
      returned with new `l1_scope` + `profileStamp`, `update_one` called
      with the matching filter/`$set`
    - Cache miss, stamp mismatch: same, after changing profile
      situations/contexts between two calls
    - `classify_relevance` raises: topic returned unchanged, `update_one`
      NOT called, no exception propagates out of `get_topic`
    - No profile found: topic returned unchanged, `classify_relevance`
      never called
    - Existing `get_topic`/router tests that don't care about `l1_scope`
      may need a `profiles_col` mock added so they don't hit a real/None
      lookup — audit `tests/unit/test_topics_router.py` for this
    - _Requirements: 3.1, 3.2, 3.4, 5.1, 5.3_

- [x] 3. Checkpoint — run `l1_scope` + `topic_service` tests
  - `test_l1_scope.py` (11 tests) and `test_topic_service_l1_scope.py`
    (5 tests) pass, plus existing `test_topics_router.py` /
    `test_topic_service_messages.py` / `test_topic_chat_service.py`
    (61 tests) unaffected.

- [x] 4. Thread `l1_scope` through context assembly into the prompt
  - [x] 4.1 Add `l1_scope` parameter to `context_assembler.assemble()`
    - `async def assemble(user_id: str, topic: str, query: str, l1_scope:
      list[dict] | None = None) -> dict` — passed straight through into the
      returned dict as `"l1_scope": l1_scope`, no new fetch inside
      `assemble()` itself
    - _Requirements: 4.2_

  - [x] 4.2 Update the call site in `TopicChatService.handle_message()`
    - `unified-backend/app/services/topic_chat_service.py:227` —
      `context = await context_assembler.assemble(user_id, topic_title,
      content, l1_scope=topic.get("l1_scope"))`; `topic` here is already the
      `get_topic()` result from line 198, so `l1_scope` is current by
      construction
    - Leave `app/routers/mentor.py:67`'s call to `assemble()` unchanged — it
      has no topic document to source `l1_scope` from (documented known
      limitation, design.md Overview)
    - _Requirements: 4.2_

  - [x] 4.3 Update `prompt_store.py::_format_learning_context()`
    - New signature: `_format_learning_context(profile: dict, l1_scope:
      list[dict] | None = None) -> str`
    - Replace its inline contexts/situations/label extraction with
      `extract_situations_and_contexts(profile)` from `l1_scope.py` (task
      1.1) — deletes the duplicated logic
    - `if l1_scope is not None:` filter `situations`/`contexts` to only
      entries whose text appears in `{j["situation"] for j in l1_scope if
      j.get("relevant")}` — else (i.e. `l1_scope is None`) leave both lists
      unfiltered, preserving today's behavior exactly
    - _Requirements: 4.1, 4.3, 5.2_

  - [x] 4.4 Update `_build_context_variables()` call site
    - `"learning_context": _format_learning_context(profile,
      context.get("l1_scope")),`
    - _Requirements: 4.2_

  - [x]* 4.5 Write tests
    - `test_topic_chat_service.py`: assert `context_assembler.assemble` is
      called with `l1_scope=topic["l1_scope"]` (mock assertion on call args)
    - `test_prompt_store.py`, new `TestFormatLearningContext` class:
      - `l1_scope=None` — output identical to today's (regression against
        current fixtures/expected strings)
      - `l1_scope=[]` — `"Not specified"`
      - `l1_scope` with a mix of `relevant: True`/`False` — only the
        `True` entries' text appears in the output
      - `l1_scope` where every entry is `relevant: False` — `"Not
        specified"`, NOT a fallback to the unfiltered lists (Property 4)
    - _Requirements: 4.1, 4.2, 4.3, 5.2_

- [x] 5. Final checkpoint — run full backend test suite
  - Full `pytest` from `unified-backend/`: 742 passed.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
  delivery — but 2.4 and 4.5 cover the exact two bugs found in design
  review (silent text-drift filtering, failed-attempt-looks-fresh), so
  skipping them trades away the regression coverage for the fixes this spec
  exists to make correct.
- No database migration: `l1_scope`/`profileStamp` are additive-optional
  fields, backfilled lazily on first `get_topic()` call per topic.
- `app/routers/mentor.py` is explicitly not touched — see design.md's
  "Known limitation" note. Nothing in the frontend calls it.
- The `SubtopicGeneratorAgent` (reuses `l1_scope` once this ships) is a
  separate spec, not part of this task list.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["2.3"] },
    { "id": 5, "tasks": ["2.4", "3"] },
    { "id": 6, "tasks": ["4.1"] },
    { "id": 7, "tasks": ["4.2", "4.3"] },
    { "id": 8, "tasks": ["4.4"] },
    { "id": 9, "tasks": ["4.5"] },
    { "id": 10, "tasks": ["5"] }
  ]
}
```
