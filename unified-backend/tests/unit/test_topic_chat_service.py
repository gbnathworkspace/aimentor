"""Unit tests for TopicChatService.

Tests cover:
- handle_message happy path (user message appended, LLM called, assistant message appended)
- LLM timeout returns error dict, user message preserved
- LLM exception returns error dict, user message preserved
- Post-turn hook triggers compaction check
- Post-turn hook failure doesn't crash the service
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.topic_chat_service import TopicChatService, LLM_TIMEOUT_SECONDS


def _mock_count_tokens(text: str) -> int:
    """Simple heuristic: ~4 chars per token."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@pytest.fixture(autouse=True)
def mock_tiktoken():
    """Mock tiktoken's count_tokens to avoid network calls."""
    with patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens):
        yield


@pytest.fixture
def mock_topic_service():
    """Mock TopicService with standard behavior."""
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
def mock_compaction_service():
    """Mock CompactionService."""
    service = AsyncMock()
    service.should_compact = AsyncMock(return_value=False)
    service.compact = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_token_counter():
    """Mock TokenCounter."""
    counter = MagicMock()
    counter.count_message.return_value = 5
    counter.get_usage_percent.return_value = 0
    return counter


@pytest.fixture
def chat_service(mock_topic_service, mock_compaction_service, mock_token_counter):
    """Create a TopicChatService with mocked dependencies."""
    return TopicChatService(
        topic_service=mock_topic_service,
        compaction_service=mock_compaction_service,
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
        """User message is appended, LLM called, assistant message appended."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {"goal": "Learn graphs"},
            "skill": {},
            "episodes": [],
            "documents": [],
        })
        mock_get_prompt.return_value = "You are a mentor."

        # Mock the LLM call
        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Here's my response about graphs."

            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Explain BFS", mode="topic"
            )

        # Verify success response
        assert "response" in result
        assert result["response"] == "Here's my response about graphs."
        assert "error" not in result

        # Verify user message was appended (first call)
        first_append_call = mock_topic_service.append_message.call_args_list[0]
        assert first_append_call[0][0] == "topic-abc"
        assert first_append_call[0][1] == "user-123"
        user_msg = first_append_call[0][2]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Explain BFS"

        # Verify assistant message was appended (second call)
        second_append_call = mock_topic_service.append_message.call_args_list[1]
        assistant_msg = second_append_call[0][2]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"] == "Here's my response about graphs."

        # The exact L1/L2/L3-assembled prompt for this turn is stored on the
        # message — context drifts over time, so it's only recoverable if
        # captured live, not reconstructable later from current profile/skill state.
        assert assistant_msg["systemPrompt"] == "You are a mentor."

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_happy_path_calls_context_assembler(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        """Context assembler is called with user_id, topic_title, and content."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {"goal": "Learn"},
            "skill": {},
            "episodes": [],
            "documents": [],
        })
        mock_get_prompt.return_value = "System prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Response"
            await chat_service.handle_message(
                "topic-abc", "user-123", "What is DFS?", mode="doubt"
            )

        mock_assembler.assemble.assert_called_once_with("user-123", "Test Topic", "What is DFS?")
        mock_get_prompt.assert_called_once_with("doubt", mock_assembler.assemble.return_value)

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_happy_path_returns_response_dict(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        """Successful call returns dict with 'response' key."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "LLM says hello"
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hi"
            )

        assert result == {"response": "LLM says hello", "suggestions": []}


class TestHandleMessageHardCap:
    """Tests for the hard token-capacity cap (backstop when compaction fails)."""

    @pytest.mark.asyncio
    async def test_over_capacity_rejects_without_llm_call(
        self, chat_service, mock_topic_service, mock_token_counter
    ):
        """At/over 100% usage, the message is rejected before any append or LLM call."""
        mock_token_counter.get_usage_percent.return_value = 100

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hello", mode="topic"
            )

        assert result["topicFull"] is True
        assert "error" in result
        mock_topic_service.append_message.assert_not_called()
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_under_capacity_proceeds_normally(
        self, mock_get_prompt, mock_assembler, chat_service, mock_token_counter
    ):
        """Below the cap, the turn proceeds as usual."""
        mock_token_counter.get_usage_percent.return_value = 99
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Response"
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hello"
            )

        assert result["response"] == "Response"


class TestHandleMessageLLMTimeout:
    """Tests for LLM timeout handling (Req 4.4)."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_timeout_returns_error_dict(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        """LLM timeout returns error dict and user message is preserved."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = asyncio.TimeoutError()

            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hello"
            )

        # Should return error
        assert "error" in result
        assert "could not be generated" in result["error"]
        assert "response" not in result

        # User message was still appended (first call)
        assert mock_topic_service.append_message.call_count == 1
        user_msg = mock_topic_service.append_message.call_args_list[0][0][2]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Hello"

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_timeout_does_not_append_assistant_message(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        """On timeout, no assistant message is appended."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = asyncio.TimeoutError()
            await chat_service.handle_message("topic-abc", "user-123", "Hello")

        # Only 1 append call (user message), not 2
        assert mock_topic_service.append_message.call_count == 1


class TestHandleMessageLLMException:
    """Tests for LLM exception handling (Req 4.4)."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_llm_exception_returns_error_dict(
        self, mock_get_prompt, mock_assembler, chat_service, mock_topic_service
    ):
        """LLM exception (non-timeout) returns error dict, user message preserved."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("Anthropic API error: rate limit")

            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Explain Dijkstra"
            )

        assert "error" in result
        assert "could not be generated" in result["error"]

        # User message was appended
        assert mock_topic_service.append_message.call_count == 1
        user_msg = mock_topic_service.append_message.call_args_list[0][0][2]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Explain Dijkstra"

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_anthropic_api_error_returns_error_dict(
        self, mock_get_prompt, mock_assembler, chat_service
    ):
        """Specific Anthropic API errors are caught and return error dict."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("Connection refused")

            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hello"
            )

        assert "error" in result


class TestPostTurnHook:
    """Tests for the post-turn compaction hook (Req 6.4, 14.1)."""

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_post_turn_hook_triggers_compaction_check(
        self, mock_get_prompt, mock_assembler, chat_service, mock_compaction_service
    ):
        """After a successful response, shouldCompact is called."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "LLM response"
            await chat_service.handle_message("topic-abc", "user-123", "Hello")

        # Allow the asyncio.create_task to execute
        await asyncio.sleep(0.05)

        mock_compaction_service.should_compact.assert_called_once_with(
            "topic-abc", "user-123"
        )

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_post_turn_hook_triggers_compaction_when_needed(
        self, mock_get_prompt, mock_assembler, chat_service, mock_compaction_service
    ):
        """When shouldCompact returns True, compact() is called."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"
        mock_compaction_service.should_compact.return_value = True

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "response"
            await chat_service.handle_message("topic-abc", "user-123", "Hello")

        await asyncio.sleep(0.05)

        mock_compaction_service.compact.assert_called_once_with("topic-abc", "user-123")

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_post_turn_hook_skips_compaction_when_not_needed(
        self, mock_get_prompt, mock_assembler, chat_service, mock_compaction_service
    ):
        """When shouldCompact returns False, compact() is not called."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"
        mock_compaction_service.should_compact.return_value = False

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "response"
            await chat_service.handle_message("topic-abc", "user-123", "Hello")

        await asyncio.sleep(0.05)

        mock_compaction_service.compact.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.topic_chat_service.context_assembler")
    @patch("app.services.topic_chat_service.get_system_prompt")
    async def test_post_turn_hook_failure_does_not_crash_service(
        self, mock_get_prompt, mock_assembler, chat_service, mock_compaction_service
    ):
        """Post-turn hook failure doesn't affect the response to the user."""
        mock_assembler.assemble = AsyncMock(return_value={
            "profile": {}, "skill": {}, "episodes": [], "documents": [],
        })
        mock_get_prompt.return_value = "prompt"
        mock_compaction_service.should_compact.side_effect = Exception("DB down")

        with patch.object(chat_service, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "All good"

            # The main response should still succeed
            result = await chat_service.handle_message(
                "topic-abc", "user-123", "Hello"
            )

        # Allow the task to execute and handle the exception
        await asyncio.sleep(0.05)

        # Main response is still successful
        assert result == {"response": "All good", "suggestions": []}

    @pytest.mark.asyncio
    async def test_post_turn_hook_direct_call_logs_error(
        self, chat_service, mock_compaction_service
    ):
        """Direct _post_turn_hook call catches and logs exceptions."""
        mock_compaction_service.should_compact.side_effect = RuntimeError("connection lost")

        # Should not raise
        await chat_service._post_turn_hook("topic-abc", "user-123", 2)

        # Verify should_compact was called (it raised but was caught)
        mock_compaction_service.should_compact.assert_called_once()


class TestFormatMessagesForApi:
    """Tests for _format_messages_for_api conversion logic."""

    @pytest.fixture
    def service(self, mock_topic_service, mock_compaction_service, mock_token_counter):
        return TopicChatService(
            topic_service=mock_topic_service,
            compaction_service=mock_compaction_service,
            token_counter=mock_token_counter,
        )

    def test_regular_messages_pass_through(self, service):
        """Regular user/assistant messages are passed through."""
        messages = [
            {"type": "message", "role": "user", "content": "Hello"},
            {"type": "message", "role": "assistant", "content": "Hi there"},
        ]
        result = service._format_messages_for_api(messages)
        assert result[0] == {"role": "user", "content": "Hello"}
        # Last message gets a cache_control breakpoint (issue #23 caching)
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == [{
            "type": "text",
            "text": "Hi there",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_summary_blocks_converted_to_assistant_messages(self, service):
        """SummaryBlocks become assistant messages with summary prefix."""
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
        # Last message gets a cache_control breakpoint (issue #23 caching)
        assert result[2]["content"] == [{
            "type": "text",
            "text": "Now about Dijkstra",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_first_message_must_be_user(self, service):
        """Messages before the first user message are trimmed."""
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
        """Legacy 'mentor' role is converted to 'assistant'."""
        messages = [
            {"type": "message", "role": "user", "content": "Question"},
            {"type": "message", "role": "mentor", "content": "Answer"},
        ]
        result = service._format_messages_for_api(messages)
        assert result[1]["role"] == "assistant"

    def test_window_capped_at_20_messages(self, service):
        """More than 20 messages gets trimmed to last 20."""
        messages = []
        for i in range(30):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"type": "message", "role": role, "content": f"Msg {i}"})

        result = service._format_messages_for_api(messages)
        assert len(result) <= 20
        # First message must be from user
        assert result[0]["role"] == "user"

    def test_empty_messages_returns_empty(self, service):
        """Empty input returns empty output."""
        result = service._format_messages_for_api([])
        assert result == []


class TestBuildSystemBlocks:
    """_build_system_blocks splits on the static/L1 boundary markers for caching (issue #23)."""

    @pytest.fixture
    def service(self, mock_topic_service, mock_compaction_service, mock_token_counter):
        return TopicChatService(
            topic_service=mock_topic_service,
            compaction_service=mock_compaction_service,
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
