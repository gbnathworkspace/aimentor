"""Unit tests for TopicChatService.

Tests cover:
- handle_message happy path (user message appended, LLM streamed, assistant message appended)
- LLM failure mid-stream yields an in-band error marker, user message preserved
- Post-turn hook triggers compaction check after the stream ends
- Post-turn hook failure doesn't crash the service
- Tool loop: search_documents/search_other_topics executed mid-turn, then a final answer
- Loop is capped at _MAX_LOOP_ROUNDS regardless of further tool_calls
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk

from app.services.topic_chat_service import (
    TopicChatService,
    LLM_TIMEOUT_SECONDS,
    _META_MARKER,
    _MAX_LOOP_ROUNDS,
)


def _chunk(text: str = "", tool_calls: list | None = None) -> AIMessageChunk:
    """Build a single-chunk fake astream() response — our accumulation loop
    handles any number of chunks, one is enough to exercise the logic
    without replicating real incremental tool-call-chunk merging."""
    content = [{"type": "text", "text": text}] if text else []
    return AIMessageChunk(content=content, tool_calls=tool_calls or [])


async def _astream(chunks: list[AIMessageChunk]):
    for c in chunks:
        yield c


def _tool_call(name: str, args: dict, call_id: str = "tc-1") -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _mock_chat_anthropic(round_chunks: list[list[AIMessageChunk]]) -> MagicMock:
    """Patch target for ChatAnthropic: each call to `.astream()` (one per
    loop round) returns the next pre-built stream in `round_chunks`, in order."""
    mock_llm = MagicMock()
    mock_llm.astream = MagicMock(side_effect=[_astream(cs) for cs in round_chunks])
    cls = MagicMock()
    cls.return_value.bind_tools.return_value = mock_llm
    return cls


async def _collect_stream(result) -> str:
    assert isinstance(result, StreamingResponse)
    return "".join([piece async for piece in result.body_iterator])


def _split_meta(full: str):
    idx = full.find(_META_MARKER)
    if idx == -1:
        return full, None
    return full[:idx], json.loads(full[idx + len(_META_MARKER):])


def _mock_count_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


@pytest.fixture(autouse=True)
def mock_tiktoken():
    with patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens):
        yield


@pytest.fixture
def mock_topic_service():
    service = AsyncMock()
    service.append_message = AsyncMock(return_value={
        "type": "message",
        "id": "msg-123",
        "role": "user",
        "content": "Hello",
        "timestamp": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        "tokenCount": 3,
    })
    service.get_topic = AsyncMock(return_value={
        "topicId": "topic-abc",
        "userId": "user-123",
        "title": "Test Topic",
        "status": "active",
        "messages": [
            {
                "type": "message",
                "id": "msg-1",
                "role": "user",
                "content": "Hello",
                "timestamp": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
                "tokenCount": 3,
            }
        ],
    })
    return service


@pytest.fixture
def mock_token_counter():
    counter = MagicMock()
    counter.count_message.return_value = 5
    counter.get_usage_percent.return_value = 0
    return counter


@pytest.fixture
def chat_service(mock_topic_service, mock_token_counter):
    return TopicChatService(
        topic_service=mock_topic_service,
        token_counter=mock_token_counter,
    )


class TestHandleMessageHappyPath:
    """Tests for the successful handle_message flow."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_happy_path_appends_user_and_assistant_messages(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {"goal": "Learn graphs"}, "skill": {}, "episodes": [],
            "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "You are a mentor."

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Here's my response about graphs.")]]),
        ):
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Explain BFS", mode="topic"
            )
            full = await _collect_stream(result)

        visible, meta = _split_meta(full)
        assert visible == "Here's my response about graphs."
        assert meta is not None

        first_append_call = mock_topic_service.append_message.call_args_list[0]
        assert first_append_call[0][0] == "topic-abc"
        assert first_append_call[0][1] == "user-123"
        user_msg = first_append_call[0][2]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Explain BFS"

        second_append_call = mock_topic_service.append_message.call_args_list[1]
        assistant_msg = second_append_call[0][2]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"] == "Here's my response about graphs."
        assert assistant_msg["systemPrompt"] == "You are a mentor."

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_happy_path_calls_context_assembler(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {"goal": "Learn"}, "skill": {}, "episodes": [],
            "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "System prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Response")]]),
        ):
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "What is DFS?", mode="topic"
            )
            await _collect_stream(result)

        mock_assembler.assemble.assert_called_once_with(
            "user-123", "Test Topic", "What is DFS?", topic_id="topic-abc",
            l1_scope=None, summary_blocks=None,
        )
        mock_get_prompt.assert_called_once_with("diagnostic", mock_assembler.assemble.return_value)

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_threads_topic_l1_scope_into_assemble(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        """When get_topic() returns a topic carrying an l1_scope and
        summaryBlocks, they're passed straight through to
        context_assembler.assemble(). taught_concepts is no longer among
        them — it now lives on skill_graph and assemble() reads it there."""
        scope = [{"situation": "preparing for interviews", "relevant": True, "reason": "x"}]
        blocks = [{"blockId": "b1", "text": "did stuff"}]
        mock_topic_service.get_topic.return_value = {
            "topicId": "topic-abc", "userId": "user-123", "title": "Test Topic",
            "status": "active", "messages": [], "l1_scope": scope,
            "summaryBlocks": blocks,
        }
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "System prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Response")]]),
        ):
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "What is DFS?", mode="topic"
            )
            await _collect_stream(result)

        mock_assembler.assemble.assert_called_once_with(
            "user-123", "Test Topic", "What is DFS?", topic_id="topic-abc",
            l1_scope=scope, summary_blocks=blocks,
        )

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_happy_path_returns_visible_text_and_metadata(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("LLM says hello")]]),
        ):
            result = await chat_service.handle_message("topic-abc", "user-123", "Hi")
            full = await _collect_stream(result)

        visible, meta = _split_meta(full)
        assert visible == "LLM says hello"
        assert meta == {"mode": "diagnostic", "suggestions": []}

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_suggestions_fence_mid_reply_is_never_shown_raw(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        """Regression: model puts the fence before more prose, not last.

        A fixed trailing buffer only hides a fence that arrives at the very
        end of the stream. If the model keeps talking after the fence, that
        later text pushes the fence out of the buffer and it leaks to the
        client as raw markdown before the client-side META split can help.
        """
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        reply = (
            "Is that the one?\n\n"
            '```json suggestions\n[{"title": "Yes", "description": "Confirm"}]\n```\n\n'
            "Assuming it's this one, here's the breakdown in simple steps."
        )
        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk(reply)]]),
        ):
            result = await chat_service.handle_message("topic-abc", "user-123", "Hi")
            full = await _collect_stream(result)

        visible, meta = _split_meta(full)
        assert "```json" not in visible
        assert visible == (
            "Is that the one?\n\n\n\nAssuming it's this one, here's the breakdown in simple steps."
        )
        assert meta["suggestions"] == [{"title": "Yes", "description": "Confirm"}]


class TestHandleMessageHardCap:
    """Tests for the hard token-capacity cap (backstop when compaction fails)."""

    @pytest.mark.asyncio
    async def test_over_capacity_rejects_without_llm_call(
        self, chat_service, mock_topic_service, mock_token_counter
    ):
        mock_token_counter.get_usage_percent.return_value = 100
        mock_cls = _mock_chat_anthropic([])

        with patch("app.services.topic_chat_service.ChatAnthropic", mock_cls):
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hello", mode="topic"
            )

        assert result["topicFull"] is True
        assert "error" in result
        mock_topic_service.append_message.assert_not_called()
        mock_cls.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_under_capacity_proceeds_normally(
        self, mock_get_prompt, mock_assembler, chat_service, mock_token_counter
    ):
        mock_token_counter.get_usage_percent.return_value = 99
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Response")]]),
        ):
            result = await chat_service.handle_message("topic-abc", "user-123", "Hello")
            full = await _collect_stream(result)

        visible, _ = _split_meta(full)
        assert visible == "Response"


class TestHandleMessageStreamFailure:
    """LLM failure mid-stream yields an in-band error marker (Req 4.4)."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_astream_exception_yields_error_marker(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        async def _raising_astream(*args, **kwargs):
            raise RuntimeError("Anthropic API error: rate limit")
            yield  # pragma: no cover - makes this an async generator

        mock_llm = MagicMock()
        mock_llm.astream = MagicMock(side_effect=_raising_astream)
        cls = MagicMock()
        cls.return_value.bind_tools.return_value = mock_llm

        with patch("app.services.topic_chat_service.ChatAnthropic", cls):
            result = await chat_service.handle_message("topic-abc", "user-123", "Hello")
            full = await _collect_stream(result)

        assert "[error: the mentor response was interrupted" in full

        # User message was appended (before streaming started); no assistant message.
        assert mock_topic_service.append_message.call_count == 1
        user_msg = mock_topic_service.append_message.call_args_list[0][0][2]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Hello"

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_time_budget_exceeded_yields_error_marker(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("partial")]]),
        ), patch("app.services.topic_chat_service.LLM_TIMEOUT_SECONDS", -1):
            result = await chat_service.handle_message("topic-abc", "user-123", "Hello")
            full = await _collect_stream(result)

        assert "[error: the mentor response was interrupted" in full


class TestPostTurnHook:
    """Tests for the post-turn hard-ceiling check (Req 6.4, 14.1). Actual
    compaction now only ever runs at a session boundary (session_compactor);
    this hook only ever calls maybe_force_close_long_session."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_post_turn_hook_calls_force_close_check(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("LLM response")]]),
        ), patch(
            "app.services.topic_chat_service.maybe_force_close_long_session", new=AsyncMock()
        ) as mock_force_close:
            result = await chat_service.handle_message("topic-abc", "user-123", "Hello")
            await _collect_stream(result)

            await asyncio.sleep(0.05)

            mock_force_close.assert_called_once()
            assert mock_force_close.call_args.args[0] == "topic-abc"
            assert mock_force_close.call_args.args[1] == "user-123"

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_post_turn_hook_failure_does_not_crash_service(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("All good")]]),
        ), patch(
            "app.services.topic_chat_service.maybe_force_close_long_session",
            new=AsyncMock(side_effect=Exception("DB down")),
        ):
            result = await chat_service.handle_message("topic-abc", "user-123", "Hello")
            full = await _collect_stream(result)

            await asyncio.sleep(0.05)

        visible, meta = _split_meta(full)
        assert visible == "All good"
        assert meta == {"mode": "diagnostic", "suggestions": []}

    @pytest.mark.asyncio
    async def test_post_turn_hook_direct_call_logs_error(self, chat_service):
        with patch(
            "app.services.topic_chat_service.maybe_force_close_long_session",
            new=AsyncMock(side_effect=RuntimeError("connection lost")),
        ) as mock_force_close:
            await chat_service._post_turn_hook("topic-abc", "user-123")

            mock_force_close.assert_called_once()


class TestFormatMessagesForApi:
    """Tests for _format_messages_for_api conversion logic (unchanged)."""

    @pytest.fixture
    def service(self, mock_topic_service, mock_token_counter):
        return TopicChatService(
            topic_service=mock_topic_service,
            token_counter=mock_token_counter,
        )

    def test_regular_messages_pass_through(self, service):
        messages = [
            {"type": "message", "role": "user", "content": "Hello"},
            {"type": "message", "role": "assistant", "content": "Hi there"},
        ]
        result = service._format_messages_for_api(messages)
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == [{
            "type": "text",
            "text": "Hi there",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_summary_blocks_converted_to_assistant_messages(self, service):
        messages = [
            {"type": "message", "role": "user", "content": "Tell me about graphs"},
            {"type": "summary", "summary": "User discussed BFS and DFS."},
            {"type": "message", "role": "user", "content": "Now about Dijkstra"},
        ]
        result = service._format_messages_for_api(messages)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert "Summary of earlier conversation" in result[1]["content"]
        assert "BFS and DFS" in result[1]["content"]
        assert result[2]["role"] == "user"
        assert result[2]["content"] == [{
            "type": "text",
            "text": "Now about Dijkstra",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_first_message_must_be_user(self, service):
        messages = [
            {"type": "message", "role": "assistant", "content": "I'm an orphan"},
            {"type": "message", "role": "user", "content": "First user msg"},
            {"type": "message", "role": "assistant", "content": "Response"},
        ]
        result = service._format_messages_for_api(messages)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "First user msg"
        assert len(result) == 2

    def test_mentor_role_normalized_to_assistant(self, service):
        messages = [
            {"type": "message", "role": "user", "content": "Question"},
            {"type": "message", "role": "mentor", "content": "Answer"},
        ]
        result = service._format_messages_for_api(messages)
        assert result[1]["role"] == "assistant"

    def test_window_capped_at_20_messages(self, service):
        messages = []
        for i in range(30):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"type": "message", "role": role, "content": f"Msg {i}"})

        result = service._format_messages_for_api(messages)
        assert len(result) <= 20
        assert result[0]["role"] == "user"

    def test_empty_messages_returns_empty(self, service):
        result = service._format_messages_for_api([])
        assert result == []

    def test_summary_covered_messages_filtered_out(self, service):
        """Raw messages already covered by a summaryBlock (sourceSessionIds)
        must be excluded from the LLM context window — they're narrated via
        the summary block instead, never deleted from the DB."""
        messages = [
            {"type": "message", "id": "m1", "role": "user", "content": "old msg"},
            {"type": "message", "id": "m2", "role": "assistant", "content": "old reply"},
            {"type": "message", "id": "m3", "role": "user", "content": "new msg"},
        ]
        summary_blocks = [{"sourceSessionIds": ["m1", "m2"]}]
        result = service._format_messages_for_api(messages, summary_blocks)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == [{
            "type": "text",
            "text": "new msg",
            "cache_control": {"type": "ephemeral"},
        }]


class TestBuildSystemBlocks:
    """_build_system_blocks splits on the static/L1 boundary markers for caching (issue #23)."""

    @pytest.fixture
    def service(self, mock_topic_service, mock_token_counter):
        return TopicChatService(
            topic_service=mock_topic_service,
            token_counter=mock_token_counter,
        )

    def test_splits_on_both_markers_into_three_cached_blocks(self, service):
        prompt = (
            "Static instructions\n<!--STATIC-BOUNDARY-->\n"
            "L1 profile stuff\n<!--L1-BOUNDARY-->\n"
            "L2/L3 volatile stuff"
        )
        blocks = service._build_system_blocks(prompt)
        assert len(blocks) == 3
        assert blocks[0]["text"] == "Static instructions"
        assert blocks[1]["text"] == "L1 profile stuff"
        assert blocks[2]["text"] == "L2/L3 volatile stuff"
        assert all(b["cache_control"] == {"type": "ephemeral"} for b in blocks)

    def test_falls_back_to_two_blocks_without_static_marker(self, service):
        prompt = "L1 profile stuff\n<!--L1-BOUNDARY-->\nL2/L3 volatile stuff"
        blocks = service._build_system_blocks(prompt)
        assert len(blocks) == 2
        assert blocks[0]["text"] == "L1 profile stuff"
        assert blocks[1]["text"] == "L2/L3 volatile stuff"

    def test_falls_back_to_single_block_without_any_marker(self, service):
        prompt = "No marker in this prompt at all"
        blocks = service._build_system_blocks(prompt)
        assert len(blocks) == 1
        assert blocks[0]["text"] == prompt
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}


class TestDiagnosticRouting:
    """Cold-start gate: unassessed topics route to DIAGNOSTIC, and a recorded
    verdict gets written to the skill graph (issue #50)."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_unassessed_skill_routes_to_diagnostic_mode(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "diagnostic prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Have you coded before?")]]),
        ):
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "teach me JS", mode="topic"
            )
            full = await _collect_stream(result)

        mock_get_prompt.assert_called_once_with("diagnostic", mock_assembler.assemble.return_value)
        _, meta = _split_meta(full)
        assert meta["mode"] == "diagnostic"

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_diagnostic_verdict_written_to_skill_graph(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "diagnostic prompt"

        verdict_call = _tool_call(
            "record_diagnostic_verdict",
            {"subtopic_updates": [{"subtopic": "Loops", "mastery": 15}]},
        )

        from app.models.skill import SubtopicMasteryUpdate

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Got it — you're a beginner.", [verdict_call])]]),
        ), patch("app.services.topic_chat_service.skill_graph_repo") as mock_repo, patch(
            "app.services.topic_chat_service.validate_subtopic_updates",
            AsyncMock(return_value=[SubtopicMasteryUpdate(subtopic="Loops", mastery=15)]),
        ):
            mock_repo.apply_update = AsyncMock()
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "no I've never coded", mode="topic"
            )
            await _collect_stream(result)

        mock_repo.apply_update.assert_called_once()
        called_user_id, called_topic, subtopic_updates = mock_repo.apply_update.call_args[0]
        assert called_user_id == "user-123"
        assert called_topic == "Test Topic"
        assert subtopic_updates[0].subtopic == "Loops"
        assert subtopic_updates[0].mastery == 15

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_tool_call_with_no_text_still_yields_and_persists_visible_reply(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        """A turn that's only a tool call (no text blocks at all) used to
        stream zero visible bytes and persist an empty assistant message —
        the client then renders nothing, no bubble and no error, so the
        mentor silently never responds. The stream must always carry
        something visible, and the persisted message must not be empty."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "diagnostic prompt"

        verdict_call = _tool_call(
            "record_diagnostic_verdict",
            {"subtopic_updates": [{"subtopic": "Loops", "mastery": 15}]},
        )

        from app.models.skill import SubtopicMasteryUpdate

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("", [verdict_call])]]),
        ), patch("app.services.topic_chat_service.skill_graph_repo") as mock_repo, patch(
            "app.services.topic_chat_service.validate_subtopic_updates",
            AsyncMock(return_value=[SubtopicMasteryUpdate(subtopic="Loops", mastery=15)]),
        ):
            mock_repo.apply_update = AsyncMock()
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "new thread spawned", mode="topic"
            )
            visible, meta = _split_meta(await _collect_stream(result))

        assert visible.strip() != ""
        assert meta is not None

        persisted = mock_topic_service.append_message.call_args_list[-1][0][2]
        assert persisted["content"].strip() != ""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_no_verdict_tool_call_skips_skill_graph_write(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "diagnostic prompt"

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("Have you coded before?")]]),
        ), patch("app.services.topic_chat_service.skill_graph_repo") as mock_repo:
            mock_repo.apply_update = AsyncMock()
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "teach me JS", mode="topic"
            )
            await _collect_stream(result)

        mock_repo.apply_update.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_assessed_skill_uses_router_decision_and_instruction_override(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {"subtopic_mastery": {"Arrays": 55}},
            "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "direct prompt"

        from app.services.mode_router import MatchedRule, MentorMode, RouterDecision

        fake_decision = RouterDecision(
            matched_rule=MatchedRule.RULE_2_URGENCY_DIRECT,
            selected_mode=MentorMode.DIRECT,
            reasoning="Pure syntax lookup.",
            instruction_override="Just give the syntax, nothing else.",
        )

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([[_chunk("array.push(x)")]]),
        ) as mock_cls, patch(
            "app.services.topic_chat_service.mode_router.route_user_turn",
            new_callable=AsyncMock,
        ) as mock_route:
            mock_route.return_value = fake_decision
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "syntax for array push", mode="topic"
            )
            await _collect_stream(result)

        mock_get_prompt.assert_called_once_with("direct", mock_assembler.assemble.return_value)
        # DIRECT is not diagnostic — no verdict tool should have been bound.
        bound_tools = mock_cls.return_value.bind_tools.call_args[0][0]
        assert all(t["name"] != "record_diagnostic_verdict" for t in bound_tools)

class TestToolLoop:
    """The mentor can call search_documents/search_other_topics mid-turn,
    see the result, and answer in a second round."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_non_loop_tool_call_short_circuits_without_looping(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        """record_diagnostic_verdict is never treated as a loop trigger —
        one round only, same as pre-streaming behavior."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [], "skill_graph": [],
        })
        mock_get_prompt.return_value = "diagnostic prompt"

        verdict_call = _tool_call(
            "record_diagnostic_verdict",
            {"subtopic_updates": [{"subtopic": "Loops", "mastery": 15}]},
        )
        round0 = [_chunk("Got it.", [verdict_call])]

        from app.models.skill import SubtopicMasteryUpdate

        with patch(
            "app.services.topic_chat_service.ChatAnthropic",
            _mock_chat_anthropic([round0]),
        ) as mock_cls, patch("app.services.topic_chat_service.skill_graph_repo") as mock_repo, patch(
            "app.services.topic_chat_service.validate_subtopic_updates",
            AsyncMock(return_value=[SubtopicMasteryUpdate(subtopic="Loops", mastery=15)]),
        ):
            mock_repo.apply_update = AsyncMock()
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "no I've never coded", mode="topic"
            )
            full = await _collect_stream(result)

        assert mock_cls.return_value.bind_tools.call_count == 1
        visible, _ = _split_meta(full)
        assert visible == "Got it."
        mock_repo.apply_update.assert_called_once()
