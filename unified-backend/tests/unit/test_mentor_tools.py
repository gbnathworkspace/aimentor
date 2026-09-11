"""Unit tests for app/services/mentor_tools.py — the mentor's LangChain toolkit."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_anthropic.chat_models import convert_to_anthropic_tool

from app.models.skill import SubtopicMasteryUpdate
from app.services.mentor_tools import (
    DIAGNOSTIC_VERDICT_TOOL,
    LOOP_TOOL_NAMES,
    LOOP_TOOLS,
    TurnState,
    run_tool,
)

_QUERY_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
_NO_INPUT_SCHEMA = {"type": "object", "properties": {}}

# Frozen copy of the hand-written tool dicts these LangChain tools replaced
# (topic_chat_service.py before the conversion). Names are referenced by
# mentor_v1.md, prompt_store.py and the frontend; descriptions are prompt
# text. Any drift here changes what the model sees.
GOLDEN_TOOLS = [
    {
        "name": "search_documents",
        "description": (
            "Semantically search the user's uploaded documents (résumé, notes, "
            "problem lists) for a specific query. Use this when you need a "
            "detail that isn't already in the Uploaded Documents section — the "
            "default injection is a small unranked sample, not the full set."
        ),
        "input_schema": _QUERY_SCHEMA,
    },
    {
        "name": "search_other_topics",
        "description": (
            "Semantically search the user's session history in OTHER topics "
            "for a specific query. Use this only when the user references "
            "something from a different topic that isn't already in your "
            "context — not for anything about the current topic (use "
            "get_past_sessions for that)."
        ),
        "input_schema": _QUERY_SCHEMA,
    },
    {
        "name": "get_user_profile",
        "description": (
            "Get the user's learning-context facts (background, goals, "
            "experience) and observed teaching-style notes. Call this if you "
            "need to tailor an explanation or example to who the user is or "
            "how they like to learn."
        ),
        "input_schema": _NO_INPUT_SCHEMA,
    },
    {
        "name": "get_skill_state",
        "description": (
            "Get this topic's per-subtopic mastery levels and the specific "
            "concepts already taught in this topic. Call this before deciding "
            "how much to re-explain or how to calibrate difficulty."
        ),
        "input_schema": _NO_INPUT_SCHEMA,
    },
    {
        "name": "get_past_sessions",
        "description": (
            "Get narrative summaries of this topic's own prior closed sessions. "
            "Call this if the user references something discussed before in "
            "this topic, or you need continuity with earlier sessions here."
        ),
        "input_schema": _NO_INPUT_SCHEMA,
    },
    {
        "name": "record_diagnostic_verdict",
        "description": (
            "Record mastery for the specific subtopics the user's answers gave enough "
            "signal to judge, once you have that signal. Do not call this until you're "
            "confident on at least one subtopic — it's fine to ask another question "
            "first and call it on a later turn. Only include subtopics you actually "
            "assessed this turn; do not guess at the rest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subtopic_updates": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "subtopic": {"type": "string"},
                            "mastery": {"type": "number", "minimum": 0, "maximum": 100},
                        },
                        "required": ["subtopic", "mastery"],
                    },
                },
            },
            "required": ["subtopic_updates"],
        },
    },
]


@pytest.fixture(autouse=True)
def trace():
    with patch("app.services.mentor_tools.write_trace", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def turn():
    return TurnState(user_id="u1", topic_title="JavaScript")


class TestSchemaParity:
    def test_model_visible_schemas_match_pre_conversion_dicts(self):
        generated = [convert_to_anthropic_tool(t) for t in [*LOOP_TOOLS, DIAGNOSTIC_VERDICT_TOOL]]
        assert generated == GOLDEN_TOOLS

    def test_no_injected_state_in_any_schema(self):
        for t in [*LOOP_TOOLS, DIAGNOSTIC_VERDICT_TOOL]:
            properties = convert_to_anthropic_tool(t)["input_schema"]["properties"]
            assert not {"turn", "user_id", "context", "topic_title"} & set(properties)

    def test_verdict_is_not_a_loop_tool(self):
        assert LOOP_TOOL_NAMES == {
            "search_documents", "search_other_topics",
            "get_user_profile", "get_skill_state", "get_past_sessions",
        }
        assert DIAGNOSTIC_VERDICT_TOOL.name not in LOOP_TOOL_NAMES


class TestInjection:
    @pytest.mark.asyncio
    async def test_model_supplied_user_or_turn_cannot_override_injected_turn(self, turn):
        attacker = TurnState(user_id="attacker", topic_title="x")
        with patch("app.services.mentor_tools.vector_search", AsyncMock(return_value=[])) as mock_search:
            await run_tool(
                "search_documents",
                {"query": "salary", "user_id": "attacker", "turn": attacker},
                turn,
            )
        mock_search.assert_awaited_once_with("salary", "u1", source="ingestion", limit=5)

    @pytest.mark.asyncio
    async def test_concurrent_turns_stay_isolated(self):
        async def _search(query, user_id, source, limit):
            await asyncio.sleep(0)
            return [{"text": f"doc of {user_id}"}]

        with patch("app.services.mentor_tools.vector_search", side_effect=_search):
            results = await asyncio.gather(
                run_tool("search_documents", {"query": "q"}, TurnState("u1", "T")),
                run_tool("search_documents", {"query": "q"}, TurnState("u2", "T")),
            )
        assert results == ["doc of u1", "doc of u2"]


class TestSearchTools:
    @pytest.mark.asyncio
    async def test_search_documents_uses_ingestion_source_and_joins_results(self, turn):
        hits = [{"text": "résumé line"}, {"text": "notes line"}]
        with patch("app.services.mentor_tools.vector_search", AsyncMock(return_value=hits)) as mock_search:
            result = await run_tool("search_documents", {"query": "experience"}, turn)
        mock_search.assert_awaited_once_with("experience", "u1", source="ingestion", limit=5)
        assert result == "résumé line\n\nnotes line"

    @pytest.mark.asyncio
    async def test_search_other_topics_uses_summary_block_source(self, turn):
        with patch("app.services.mentor_tools.vector_search", AsyncMock(return_value=[{"text": "s"}])) as mock_search:
            result = await run_tool("search_other_topics", {"query": "closures"}, turn)
        mock_search.assert_awaited_once_with("closures", "u1", source="summary_block", limit=5)
        assert result == "s"

    @pytest.mark.asyncio
    async def test_empty_results_messages(self, turn):
        with patch("app.services.mentor_tools.vector_search", AsyncMock(return_value=[])):
            docs = await run_tool("search_documents", {"query": "q"}, turn)
            sessions = await run_tool("search_other_topics", {"query": "q"}, turn)
        assert docs == "No matching documents found."
        assert sessions == "No matching past sessions found."


class TestContextTools:
    """L1/L2/L3 served on demand from the already-assembled context, no I/O,
    same strings the old static injection produced."""

    @pytest.mark.asyncio
    async def test_get_user_profile_formats_learning_context_and_style_notes(self):
        context = {
            "profile": {
                "learning_context_detail": {"situations": ["Backend engineer"]},
                "style_notes": [{"category": "communication", "note": "Use analogies"}],
            },
        }
        with patch("app.services.mentor_tools.vector_search", AsyncMock()) as mock_search:
            result = await run_tool("get_user_profile", {}, TurnState("u1", "T", context))
        assert "Backend engineer" in result
        assert "Use analogies" in result
        mock_search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_skill_state_formats_mastery_and_taught_concepts(self):
        context = {
            "skill": {"subtopic_mastery": {"Loops": 40}},
            "taught_concepts": ["for vs while"],
        }
        result = await run_tool("get_skill_state", {}, TurnState("u1", "T", context))
        assert "Loops: 40%" in result
        assert "for vs while" in result

    @pytest.mark.asyncio
    async def test_get_past_sessions_formats_summary_blocks(self):
        context = {"summary_blocks": [{"text": "Covered recursion basics", "createdAt": "2025-01-01"}]}
        result = await run_tool("get_past_sessions", {}, TurnState("u1", "T", context))
        assert "Covered recursion basics" in result

    @pytest.mark.asyncio
    async def test_missing_context_falls_back_to_placeholders(self, turn):
        result = await run_tool("get_skill_state", {}, turn)
        assert "not assessed yet" in result
        assert "nothing recorded yet" in result


class TestFailureModes:
    @pytest.mark.asyncio
    async def test_tool_exception_returns_fail_open_text(self, turn):
        with patch("app.services.mentor_tools.vector_search", AsyncMock(side_effect=RuntimeError("atlas down"))):
            result = await run_tool("search_documents", {"query": "q"}, turn)
        assert result == "Lookup failed for search_documents — proceed without this information."

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_unknown_text_without_trace(self, turn, trace):
        assert await run_tool("web_search", {}, turn) == "Unknown tool: web_search"
        trace.assert_not_awaited()


class TestDiagnosticVerdict:
    @pytest.mark.asyncio
    async def test_raw_updates_reach_validator_unfiltered(self, turn):
        raw = [{"subtopic": "Loops", "mastery": 15}, {"subtopic": "Closures", "mastery": 150}]
        validated = [SubtopicMasteryUpdate(subtopic="Loops", mastery=15)]
        with patch(
            "app.services.mentor_tools.validate_subtopic_updates", AsyncMock(return_value=validated),
        ) as mock_validate, patch("app.services.mentor_tools.skill_graph_repo") as mock_repo:
            mock_repo.apply_update = AsyncMock()
            result = await run_tool("record_diagnostic_verdict", {"subtopic_updates": raw}, turn)

        mock_validate.assert_awaited_once_with("JavaScript", raw)
        mock_repo.apply_update.assert_awaited_once_with("u1", "JavaScript", validated)
        assert result == "Recorded mastery for 1 subtopic(s)."

    @pytest.mark.asyncio
    async def test_extra_model_key_does_not_raise(self, turn):
        with patch(
            "app.services.mentor_tools.validate_subtopic_updates", AsyncMock(return_value=[]),
        ), patch("app.services.mentor_tools.skill_graph_repo") as mock_repo:
            mock_repo.apply_update = AsyncMock()
            result = await run_tool(
                "record_diagnostic_verdict",
                {"subtopic_updates": [{"subtopic": "Loops", "mastery": 15}], "confidence": "high"},
                turn,
            )
        assert result == "Recorded mastery for 0 subtopic(s)."

    @pytest.mark.asyncio
    async def test_write_failure_is_fail_open(self, turn):
        with patch(
            "app.services.mentor_tools.validate_subtopic_updates",
            AsyncMock(side_effect=RuntimeError("subtopic decomposition failed")),
        ):
            result = await run_tool("record_diagnostic_verdict", {"subtopic_updates": []}, turn)
        assert result.startswith("Lookup failed for record_diagnostic_verdict")


class TestTracing:
    @pytest.mark.asyncio
    async def test_successful_execution_is_traced(self, turn, trace):
        with patch("app.services.mentor_tools.vector_search", AsyncMock(return_value=[{"text": "hit"}])):
            await run_tool("search_documents", {"query": "résumé"}, turn)

        trace.assert_awaited_once()
        call_site, model, user_id, prompt = trace.call_args.args
        assert (call_site, model, user_id) == ("mentor_tool.search_documents", "", "u1")
        assert json.loads(prompt) == {"query": "résumé"}
        assert trace.call_args.kwargs["response"] == "hit"
        assert trace.call_args.kwargs["error"] is None

    @pytest.mark.asyncio
    async def test_failed_execution_is_traced_with_error(self, turn, trace):
        with patch("app.services.mentor_tools.vector_search", AsyncMock(side_effect=RuntimeError("atlas down"))):
            await run_tool("search_documents", {"query": "q"}, turn)

        assert trace.call_args.kwargs["error"] == "atlas down"
        assert trace.call_args.kwargs["response"] is None

    @pytest.mark.asyncio
    async def test_trace_prompt_holds_only_model_args_never_turn_state(self, trace):
        context = {"profile": {"learning_context_detail": {"situations": ["SECRET-FACT"]}}}
        await run_tool("get_user_profile", {}, TurnState("u1", "T", context))

        prompt = trace.call_args.args[3]
        assert prompt == "{}"
        assert "SECRET-FACT" not in prompt
