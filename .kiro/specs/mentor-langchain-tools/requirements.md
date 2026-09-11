# Requirements Document

## Introduction

Source: 2026-09-11 session — inventory of the APIs the agents use, followed by
the decision to convert the mentor's tools to LangChain `@tool`s.

The mentor chat (`unified-backend/app/services/topic_chat_service.py`) is the
backend's only agent loop: `claude-sonnet-5` via `ChatAnthropic.bind_tools`, up
to 2 rounds per turn. Its 7 tools are hand-written Anthropic JSON-schema dicts
(`topic_chat_service.py:48-167`), dispatched by an `if name == ...` chain in
`_execute_loop_tool` (`:523-560`), with `record_diagnostic_verdict` handled
separately in `_apply_diagnostic_verdict` (`:581-606`). Three problems follow
from that shape:

- **Not reusable.** Schemas and implementations are private to
  `TopicChatService`. Any other agent (e.g. the deferred
  `SubtopicGeneratorAgent`, see `topic-scoping/requirements.md`) would have to
  copy them.
- **Not observable.** The mentor call goes through LangChain, not
  `llm_trace.traced_messages_create`, so neither its model rounds nor its tool
  executions reach `llm_traces_col` or the admin analytics view
  (`app/auth/admin_router.py:68`). The most expensive LLM call in the backend
  is the one that isn't traced.
- **Schema and implementation drift apart.** A tool's schema lives in one
  place and its implementation in another, joined only by a string name, and
  a tool can only be tested through `_execute_loop_tool` on a constructed
  service.

This spec moves the six locally executed tools into a standalone LangChain
toolkit, keeps the existing loop, and traces model rounds and tool executions
into the existing trace store.

## Scope decisions

Resolved before writing acceptance criteria:

1. **Mentor loop tools only.** In scope: `search_documents`,
   `search_other_topics`, `get_user_profile`, `get_skill_state`,
   `get_past_sessions`, `record_diagnostic_verdict`. `mode_router`,
   `topic_router` and `session_compactor` use forced `tool_use` as a
   structured-output trick rather than as tools, and stay on the raw SDK per
   `design_decisions/15_llm_orchestration.md`.
2. **`web_search` stays a dict.** It's an Anthropic server tool
   (`web_search_20250305`) that runs on Anthropic's side; there's no local
   function to decorate.
3. **Keep the hand-rolled loop.** No LangGraph, no `create_agent`. Streaming,
   the suggestions-fence holdback, `_TOOL_MARKER` events and the 50s budget
   are custom and working. Only schema definition, dispatch and tracing change.
4. **`record_diagnostic_verdict` stays deferred.** It still ends the turn and
   is still written after the stream completes.
5. **No new dependency.** `@tool`, `StructuredTool` and `InjectedToolArg` ship
   in `langchain-core` 1.5.4, already installed via `langchain-anthropic>=1.5.5`
   (`requirements.txt:19`). Tracing reuses `llm_traces_col`; decision 15 ranks
   LangSmith last for tracing.

## Requirements

### Requirement 1 — Standalone mentor toolkit

**User Story:** As a developer building another agent, I want the mentor's
tools defined in their own module, so that I can bind them to a different
agent without copying code out of `TopicChatService`.

#### Acceptance Criteria

1. THE six tools SHALL each be defined as a LangChain tool (`@tool`-decorated
   function or `StructuredTool`) in one module that does not import
   `topic_chat_service`.
2. THE module SHALL be importable, and each tool invocable, without
   constructing `TopicChatService` or `ChatAnthropic`.
3. THE module SHALL expose the loop tools and the diagnostic verdict tool as
   separate groups, matching how the loop binds them today: loop tools on
   every round except the last, and the verdict tool only in DIAGNOSTIC mode.
4. `TopicChatService` SHALL no longer contain hand-written schema dicts or
   name-based dispatch for these six tools.

### Requirement 2 — Model-visible schema parity

**User Story:** As the mentor prompt, I rely on exact tool names and
descriptions, so that converting the tools must not change what the model sees.

#### Acceptance Criteria

1. Tool names SHALL be unchanged. They are referenced by name in
   `app/prompts/mentor_v1.md:18-31`, `app/services/prompt_store.py:42-56`, and
   the frontend tool-indicator labels
   (`mentorman-web/src/components/mentorman/data.ts:47-61`).
2. Tool descriptions SHALL be carried over verbatim from the current dicts
   (`topic_chat_service.py:55-159`). Descriptions are prompt text; rewording
   them is a behavior change and out of scope.
3. THE input schema sent to the model SHALL be equivalent to today's:
   - `search_documents`, `search_other_topics`: one required string `query`.
   - `get_user_profile`, `get_skill_state`, `get_past_sessions`: no properties.
   - `record_diagnostic_verdict`: required `subtopic_updates`, an array with
     `minItems: 1` whose items require a string `subtopic` and a number
     `mastery` with `minimum: 0` and `maximum: 100`.
4. A unit test SHALL assert criterion 3 against the schema actually generated
   for the bound tools (via `convert_to_anthropic_tool` or equivalent), so that
   a docstring or type-hint edit that changes the schema fails the suite.

### Requirement 3 — Per-turn state is injected, never model-controlled

**User Story:** As a user, I want the mentor's tools to only ever read my own
data, so that a prompt injection inside an uploaded document can't make the
mentor search someone else's documents.

#### Acceptance Criteria

1. `user_id` SHALL NOT appear in any tool's model-visible schema. The service
   SHALL supply it from the authenticated request.
2. THE assembled per-turn context (`context_assembler.assemble` output:
   profile, `l1_scope`, skill, `taught_concepts`, `summary_blocks`) SHALL be
   supplied by the service and SHALL NOT appear in any schema.
3. IF a model tool call's args contain a key matching an injected parameter
   (e.g. `user_id`), THEN the injected value SHALL take precedence.
4. Tools SHALL be safe under concurrent turns for different users: no
   module-level mutable state may hold a user's id or context between calls.

### Requirement 4 — Tool execution parity

**User Story:** As a user mid-conversation, I want the mentor's lookups to
return exactly what they return today, so that the refactor is invisible to me.

#### Acceptance Criteria

1. `search_documents` SHALL call `vector_search(query, user_id,
   source="ingestion", limit=5)`, and `search_other_topics` SHALL call it with
   `source="summary_block"`, `limit=5`.
2. Search results SHALL be formatted as today: each result's `text` joined by
   a blank line. Empty results SHALL return `"No matching documents found."`
   and `"No matching past sessions found."` respectively.
3. `get_user_profile`, `get_skill_state` and `get_past_sessions` SHALL perform
   no DB or network I/O. They SHALL format the injected context with
   `prompt_store.format_learning_context` + `format_style_notes`,
   `format_subtopic_mastery` + `format_taught_concepts`, and
   `format_summary_blocks` respectively, producing the same strings as today
   (`topic_chat_service.py:545-556`), including placeholders when context keys
   are missing.
4. WHEN a loop tool raises, THEN the model SHALL receive
   `"Lookup failed for {name} — proceed without this information."` and the
   turn SHALL continue.
5. WHEN the model calls a tool name that isn't bound, THEN the model SHALL
   receive `"Unknown tool: {name}"`.

### Requirement 5 — Loop integration parity

**User Story:** As the frontend, I depend on the stream's shape, so that the
loop's observable behavior must not change.

#### Acceptance Criteria

1. THE loop SHALL remain capped at `_MAX_LOOP_ROUNDS = 2`, with loop tools
   removed from the final round so the model has to answer.
2. `web_search` SHALL still be bound on every round as the server-tool dict
   with `max_uses=3`.
3. FOR each loop tool executed, THE stream SHALL emit `_TOOL_MARKER` start
   and end events in the current format (`\x00TOOL\x00{"phase": ..., "name":
   ...}\n`, parsed by `mentorman-web/src/components/mentorman/chat.tsx:20-47`),
   in order, before the next round's text.
4. Tool results SHALL be fed back as `ToolMessage`s keyed by the originating
   `tool_call_id`.
5. THE 50-second time budget, suggestions-fence holdback, empty-reply fallback
   and shielded persistence SHALL be unchanged.

### Requirement 6 — `record_diagnostic_verdict` stays deferred

**User Story:** As the skill graph, I want diagnostic verdicts written exactly
once, after the reply, through the existing validation path, so that a
half-streamed turn never records mastery.

#### Acceptance Criteria

1. `record_diagnostic_verdict` SHALL be bound only when the effective mode is
   DIAGNOSTIC.
2. A call to it SHALL NOT trigger another loop round and SHALL NOT be executed
   mid-stream.
3. AFTER the stream completes, THE service SHALL validate the call's
   `subtopic_updates` with `validate_subtopic_updates(topic_title, ...)` and
   write them with `skill_graph_repo.apply_update(user_id, topic_title,
   validated)`, the same path as today (`topic_chat_service.py:581-606`).
4. THE toolkit SHALL own the verdict's validate-and-write function so other
   agents can reuse it. The service SHALL invoke it at the deferred point.
5. A validation or write failure SHALL be logged and SHALL NOT break the turn.

### Requirement 7 — Tracing

**User Story:** As an admin, I want mentor rounds and tool calls in the
analytics trace list, so that I can see what the mentor looked up and debug a
bad turn.

#### Acceptance Criteria

1. FOR each mentor model round, THE service SHALL write one document to
   `llm_traces_col` using the existing fields (`call_site`, `model`,
   `user_id`, `prompt`, `response`, `error`, `duration_ms`, `created_at`), with
   `call_site` = `"topic_chat_service.mentor_round"`. `response` SHALL contain
   the round's visible text only (no thinking blocks). A round that raises
   SHALL still be traced, with `error` set.
2. FOR each local tool execution, including the deferred verdict write, a
   trace document SHALL be written with `call_site` = `"mentor_tool.<name>"`,
   `model` = `""`, `prompt` = the model-supplied args as JSON, and `response`
   = the result text (or `error` on failure).
3. `prompt` and `response` SHALL be truncated with `llm_trace`'s existing
   `TEXT_CHAR_LIMIT`. The injected per-turn state (including the assembled
   context) SHALL NOT be serialized into a tool trace's `prompt`, which holds
   the model's own args only, and `user_id` SHALL go only in the `user_id`
   field. A tool's result text is traced as `response` as-is, even when it is
   formatted from that context.
4. Trace writes SHALL be best-effort: a failure SHALL be logged and SHALL NOT
   interrupt the turn.
5. Trace writes SHALL NOT happen between streamed chunks of a round. They run
   after the round's stream (or the tool call) completes, so tracing adds no
   delay before the first visible token.
6. THE trace documents SHALL fit the existing schema, so that
   `admin_router.list_traces` needs no change.

### Requirement 8 — Testability

**User Story:** As a developer, I want each tool testable on its own, so that
tool changes don't require mocking a streaming LLM.

#### Acceptance Criteria

1. EACH tool SHALL have unit tests that invoke it directly (`ainvoke` with
   injected args) without `TopicChatService`, `ChatAnthropic`, or an LLM mock.
2. Tests coupled to removed internals, namely the `_execute_loop_tool` calls
   (`tests/unit/test_topic_chat_service.py:850-888`) and the dict-shaped
   `bind_tools` assertion (`:761-762`), MAY move to the new surface, but every
   behavior they assert SHALL still be asserted.
3. THE full unit suite (`tests/unit`, 723 tests at time of writing) SHALL pass.

### Requirement 9 — Record the decision

**User Story:** As a future reader of `design_decisions/`, I want the LLM
orchestration doc to match the code, so that I don't reverse or duplicate this
work based on a stale rule.

#### Acceptance Criteria

1. `design_decisions/15_llm_orchestration.md` SHALL be updated to record that
   the mentor loop runs on LangChain with a `@tool` toolkit and a hand-rolled
   loop, and why: its own "Mentor turns become agentic" trigger has fired.
   Every single-shot call stays on the raw SDK.
2. THE update SHALL also correct the doc's current "No LangChain" statement,
   which is already false: `topic_chat_service.py`, `l1_scope.py` and
   `fact_quality.py` all use `langchain-anthropic`.

## Out of scope

- Moving `mode_router`, `topic_router`, `session_compactor`, or any
  JSON-in-text call site to LangChain.
- Converting `web_search`.
- LangGraph, `create_agent`, `AgentExecutor`, or any other agent framework.
- LangSmith or Langfuse.
- Changing tool names, descriptions, prompts, or frontend tool labels.
- Tracing `l1_scope.classify_relevance` and `fact_quality.classify_fact_quality`.
  They are also untraced LangChain calls; worth a follow-up.
- Token usage or cost fields on traces.
- The legacy `routers/mentor.py` endpoint.

## Open questions (defaulted; flag if wrong)

1. **Trace granularity.** Defaulted to one document per round plus one per
   tool execution (Requirement 7). The alternative, one document per turn with
   nested tool calls, needs a new field and an admin UI change.
2. **Round trace `prompt` content.** Truncating the full message list at 4000
   chars would keep mostly the static system prompt. Default: the latest user
   message plus this round's tool results. Revisit if the admin view needs the
   system prompt.
