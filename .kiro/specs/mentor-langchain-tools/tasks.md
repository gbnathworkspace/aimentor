# Implementation Plan: Mentor LangChain Tools

## Overview

Moves the six locally executed mentor tools out of `TopicChatService` into
`app/services/mentor_tools.py` as LangChain tools with one injected
`TurnState`, adds a generic traced/fail-open `run_tool` executor, keeps the
hand-rolled 2-round streaming loop, and traces every model round and tool
call into the existing `llm_traces_col`. No new dependency, no stream-format
change.

## Tasks

- [x] 1. Make trace writing shareable (`app/services/llm_trace.py`)
  - [x] 1.1 Rename `_write_trace` → `write_trace`; move truncation inside it
    (prompt, and response when not `None`); drop truncation from
    `_extract_prompt_text` / `_extract_response_text`
    - _Requirements: 7.3, 7.4_
  - [x] 1.2 Add `tests/unit/test_llm_trace.py`
    - `write_trace` truncates prompt/response; swallows a DB error
    - `traced_messages_create` still writes one trace with truncated text
    - _Requirements: 7.3, 7.4_

- [x] 2. Create `app/services/mentor_tools.py`
  - [x] 2.1 `TurnState` frozen dataclass (`user_id`, `topic_title`, `context`)
    - _Requirements: 3.1, 3.2, 3.4_
  - [x] 2.2 Five loop tools via `@tool(name, description=CONST)` with
    `turn: Annotated[TurnState, InjectedToolArg]`; descriptions copied
    verbatim; bodies moved from `_execute_loop_tool`
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 4.1, 4.2, 4.3_
  - [x] 2.3 `record_diagnostic_verdict` with dict `args_schema` (exact
    current schema), `**_model_extras`; validates via
    `validate_subtopic_updates`, writes via `skill_graph_repo.apply_update`
    - _Requirements: 2.3, 6.3, 6.4_
  - [x] 2.4 `LOOP_TOOLS`, `LOOP_TOOL_NAMES`, `DIAGNOSTIC_VERDICT_TOOL`
    - _Requirements: 1.3_
  - [x] 2.5 `run_tool(name, args, turn)`: lookup, inject `turn` last,
    fail-open text, unknown-tool text, one `mentor_tool.<name>` trace per
    execution (model args only in `prompt`)
    - _Requirements: 3.3, 4.4, 4.5, 6.5, 7.2, 7.3, 7.4_

- [ ] 3. Add `tests/unit/test_mentor_tools.py`
  - [ ] 3.1 Golden schema test: frozen copy of today's six tool dicts ==
    `convert_to_anthropic_tool(t)`; no schema exposes `turn`/`user_id`/`context`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2_
  - [ ] 3.2 Injection: model-supplied `user_id`/`turn` can't change the
    user passed to `vector_search`; concurrent calls stay isolated
    - _Requirements: 3.3, 3.4_
  - [ ] 3.3 Execution parity: search tools' `source`/`limit`/format/empty
    text; context tools' strings + placeholders (moved from
    `TestContextTools`); fail-open; unknown tool
    - _Requirements: 4.1-4.5, 8.1, 8.2_
  - [ ] 3.4 Verdict: raw updates (incl. out-of-range item) reach
    `validate_subtopic_updates` unfiltered; `apply_update` gets validated
    list; extra model key doesn't raise
    - _Requirements: 6.3, 6.4_
  - [ ] 3.5 Tracing: call_site/model/prompt/response on success; `error` on
    failure; context never written into `prompt`
    - _Requirements: 7.2, 7.3_

- [ ] 4. Rewire `TopicChatService` (`app/services/topic_chat_service.py`)
  - [ ] 4.1 Remove the six tool dicts, `_LOOP_TOOL_NAMES`,
    `_execute_loop_tool`, `_format_search_results`,
    `_apply_diagnostic_verdict`, unused imports; add `_MENTOR_MODEL`
    - _Requirements: 1.4_
  - [ ] 4.2 Build `TurnState`; bind `[web_search, *LOOP_TOOLS, verdict?]`
    on non-final rounds and `[web_search, verdict?]` on the final round
    - _Requirements: 5.1, 5.2, 6.1_
  - [ ] 4.3 Execute loop calls through `mentor_tools.run_tool`, markers and
    `ToolMessage`s unchanged
    - _Requirements: 5.3, 5.4_
  - [ ] 4.4 Deferred verdict through `run_tool` after the stream
    - _Requirements: 6.2, 6.3, 6.5_
  - [ ] 4.5 `_trace_round`: one `topic_chat_service.mentor_round` trace per
    round (visible text only; prompt = latest user message + this round's
    tool results; `error` on a raising round), written after the round's
    stream
    - _Requirements: 7.1, 7.4, 7.5, 7.6_

- [ ] 5. Update `tests/unit/test_topic_chat_service.py`
  - [ ] 5.1 Retarget verdict patches to `app.services.mentor_tools`; make the
    bound-tool name assertion handle `BaseTool`s; remove `TestContextTools`
    (moved in 3.3)
    - _Requirements: 8.2_
  - [ ] 5.2 New: final round binds only `web_search` (+ verdict in
    diagnostic); `web_search` bound every round
    - _Requirements: 5.1, 5.2_
  - [ ] 5.3 New: one `mentor_round` trace per round; round 1 prompt carries
    the tool result; raising round traced with `error`
    - _Requirements: 7.1_

- [ ] 6. Docs and stale references
  - [ ] 6.1 Update `design_decisions/15_llm_orchestration.md`
    - _Requirements: 9.1, 9.2_
  - [ ] 6.2 Repoint `_execute_loop_tool` / `_apply_diagnostic_verdict`
    mentions in `prompt_store.py`, `test_prompt_store.py`,
    `test_subtopic_weights.py`, and `topic_chat_service.py` comments
    - _Requirements: 1.4_

- [ ] 7. Verify
  - [ ] 7.1 Full unit suite passes (`tests/unit`)
    - _Requirements: 8.3_
