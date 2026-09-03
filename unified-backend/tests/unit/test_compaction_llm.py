"""Unit tests for session_compactor._call_summarization_llm.

Tests:
- Message formatting for the prompt
- Parsing of valid tool_use response
- Handling when no skill updates are returned (empty array)
- Handling of malformed LLM response (fallback behavior)
- Anthropic client is mocked for all tests
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch env before importing app modules
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VOYAGE_API_KEY", "voy-test")

from app.services.session_compactor import (
    _call_summarization_llm,
    _format_conversation_excerpt,
    _validate_skill_updates,
)


class TestFormatConversationExcerpt:
    """Tests for _format_conversation_excerpt helper."""

    def test_formats_user_and_assistant_messages(self):
        """Messages are formatted as ROLE: content, separated by double newlines."""
        messages = [
            {"role": "user", "content": "What is BFS?"},
            {"role": "assistant", "content": "BFS stands for Breadth-First Search."},
        ]
        result = _format_conversation_excerpt(messages)
        assert "USER: What is BFS?" in result
        assert "ASSISTANT: BFS stands for Breadth-First Search." in result
        assert "\n\n" in result

    def test_handles_empty_messages(self):
        """Empty message list produces empty string."""
        result = _format_conversation_excerpt([])
        assert result == ""

    def test_handles_missing_content(self):
        """Messages with missing content default to empty string."""
        messages = [{"role": "user"}]
        result = _format_conversation_excerpt(messages)
        assert "USER: " in result

    def test_handles_missing_role(self):
        """Messages with missing role default to UNKNOWN."""
        messages = [{"content": "Hello"}]
        result = _format_conversation_excerpt(messages)
        assert "UNKNOWN: Hello" in result

    def test_multiple_messages_preserve_order(self):
        """Multiple messages are joined in order."""
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        result = _format_conversation_excerpt(messages)
        lines = result.split("\n\n")
        assert len(lines) == 3
        assert lines[0] == "USER: First"
        assert lines[1] == "ASSISTANT: Second"
        assert lines[2] == "USER: Third"


class TestValidateSkillUpdates:
    """Tests for _validate_skill_updates helper. `topic_title` is always
    supplied by the caller (never the LLM — see _call_summarization_llm),
    and subtopic-level validation itself is delegated to
    subtopic_weights.validate_subtopic_updates (mocked here, tested
    separately in test_subtopic_weights.py)."""

    @pytest.mark.asyncio
    async def test_valid_update_passes(self):
        """A well-formed skill update passes validation."""
        from app.models.skill import SubtopicMasteryUpdate

        updates = [{"subtopic": "DFS", "mastery": 40}]
        with patch(
            "app.services.subtopic_weights.validate_subtopic_updates",
            AsyncMock(return_value=[SubtopicMasteryUpdate(subtopic="DFS", mastery=40)]),
        ):
            result = await _validate_skill_updates("Graph Algorithms", updates)
        assert len(result) == 1
        assert result[0].subtopic == "DFS"

    @pytest.mark.asyncio
    async def test_all_subtopics_dropped_rejects_whole_entry(self):
        """If subtopic validation drops every proposed subtopic, nothing survives."""
        updates = [{"subtopic": "Nonsense", "mastery": 10}]
        with patch(
            "app.services.subtopic_weights.validate_subtopic_updates",
            AsyncMock(return_value=[]),
        ):
            result = await _validate_skill_updates("Graphs", updates)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_missing_topic_rejected(self):
        """An empty topic_title short-circuits to no updates (never falls back
        to a topic name the LLM proposed — there is none anymore)."""
        updates = [{"subtopic": "x", "mastery": 10}]
        result = await _validate_skill_updates("", updates)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_non_list_subtopic_updates_rejected(self):
        """A non-list skill_updates value is rejected outright (no default-empty)."""
        result = await _validate_skill_updates("Graphs", "not a list")
        assert len(result) == 0


class TestCallSummarizationLLM:
    """Tests for session_compactor._call_summarization_llm."""

    @pytest.fixture
    def sample_messages(self):
        """Sample messages for testing."""
        return [
            {"role": "user", "content": "Can you explain BFS?", "id": "m1"},
            {
                "role": "assistant",
                "content": "BFS is a graph traversal algorithm that explores neighbors first.",
                "id": "m2",
            },
            {"role": "user", "content": "How does it differ from DFS?", "id": "m3"},
            {
                "role": "assistant",
                "content": "DFS goes deep into one path before backtracking.",
                "id": "m4",
            },
        ]

    def _make_tool_use_response(self, summary: str, skill_updates: list, taught_concepts: list | None = None):
        """Create a mock Anthropic response with a tool_use block."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "compaction_result"
        tool_block.input = {
            "summary": summary,
            "skill_updates": skill_updates,
        }
        if taught_concepts is not None:
            tool_block.input["taught_concepts"] = taught_concepts

        response = MagicMock()
        response.content = [tool_block]
        return response

    @pytest.mark.asyncio
    async def test_formats_messages_into_prompt(self, sample_messages):
        """Messages are formatted and included in the LLM prompt."""
        mock_client = AsyncMock()
        mock_response = self._make_tool_use_response(
            "The student learned about BFS and DFS graph traversal algorithms.",
            [],
        )
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await _call_summarization_llm(sample_messages, "Graph Algorithms")

        # Verify messages.create was called
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]

        # Verify the prompt contains conversation content and the topic
        prompt_content = call_kwargs["messages"][0]["content"]
        assert "USER: Can you explain BFS?" in prompt_content
        assert "ASSISTANT: BFS is a graph traversal algorithm" in prompt_content
        assert "Graph Algorithms" in prompt_content

        # Verify tool is passed
        assert call_kwargs["tools"] == [_get_tool_schema()]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "compaction_result"}

    @pytest.mark.asyncio
    async def test_parses_valid_tool_use_response(self, sample_messages):
        """Valid tool_use response is parsed correctly with summary and skill updates."""
        from app.models.skill import SubtopicMasteryUpdate

        skill_updates = [{"subtopic": "DFS backtracking", "mastery": 30}]
        mock_response = self._make_tool_use_response(
            "Student explored BFS and DFS algorithms, showing good understanding of BFS queue-based traversal but struggling with DFS backtracking mechanics.",
            skill_updates,
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client), \
             patch("app.services.session_compactor.get_settings") as mock_settings, \
             patch(
                 "app.services.subtopic_weights.validate_subtopic_updates",
                 AsyncMock(return_value=[SubtopicMasteryUpdate(subtopic="DFS backtracking", mastery=30)]),
             ):
            mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
            result = await _call_summarization_llm(sample_messages, "Graph Algorithms")

        assert result["summary"].startswith("Student explored BFS and DFS")
        assert result["skill_updates"] is not None
        assert len(result["skill_updates"]) == 1
        assert result["skill_updates"][0].subtopic == "DFS backtracking"

    @pytest.mark.asyncio
    async def test_parses_taught_concepts(self, sample_messages):
        """taught_concepts entries are extracted, stripped, and non-strings dropped."""
        mock_response = self._make_tool_use_response(
            "Student learned BFS.",
            [],
            taught_concepts=["  BFS graph traversal  ", "", 42, "DFS backtracking"],
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await _call_summarization_llm(sample_messages, "Graph Algorithms")

        assert result["taught_concepts"] == ["BFS graph traversal", "DFS backtracking"]

    @pytest.mark.asyncio
    async def test_missing_taught_concepts_defaults_empty(self, sample_messages):
        """Backward-compat: a response with no taught_concepts key parses to []."""
        mock_response = self._make_tool_use_response("Student learned BFS.", [])
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await _call_summarization_llm(sample_messages, "Graph Algorithms")

        assert result["taught_concepts"] == []

    @pytest.mark.asyncio
    async def test_no_skill_updates_returns_none(self, sample_messages):
        """When LLM returns empty skill_updates array, result has None."""
        mock_response = self._make_tool_use_response(
            "Brief casual conversation about study plans without deep learning content.",
            [],
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await _call_summarization_llm(sample_messages, "Graph Algorithms")

        assert result["summary"] == "Brief casual conversation about study plans without deep learning content."
        assert result["skill_updates"] is None

    @pytest.mark.asyncio
    async def test_malformed_response_no_tool_use_block_raises(self, sample_messages):
        """If LLM response has no tool_use block, raises ValueError."""
        # Response with only a text block, no tool_use
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Some random text"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(ValueError, match="LLM response missing compaction_result tool call"):
                    await _call_summarization_llm(sample_messages, "Graph Algorithms")

    @pytest.mark.asyncio
    async def test_empty_summary_raises(self, sample_messages):
        """If LLM returns empty summary string, raises ValueError."""
        mock_response = self._make_tool_use_response("", [])

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(ValueError, match="LLM returned empty summary"):
                    await _call_summarization_llm(sample_messages, "Graph Algorithms")

    @pytest.mark.asyncio
    async def test_timeout_raises(self, sample_messages):
        """LLM timeout raises asyncio.TimeoutError which propagates."""
        import asyncio

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(asyncio.TimeoutError):
                    await _call_summarization_llm(sample_messages, "Graph Algorithms")

    @pytest.mark.asyncio
    async def test_invalid_skill_updates_filtered(self, sample_messages):
        """Subtopics that fail canonical-list validation are dropped; valid ones kept."""
        from app.models.skill import SubtopicMasteryUpdate

        skill_updates = [
            {"subtopic": "recursion", "mastery": 40},
            {"subtopic": "made up subtopic", "mastery": 50},
        ]
        mock_response = self._make_tool_use_response(
            "Learning about graph algorithms.", skill_updates
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        async def fake_validate(topic_title, raw):
            # Simulates the canonical list only recognizing "recursion".
            return [SubtopicMasteryUpdate(subtopic="recursion", mastery=40)]

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client), \
             patch("app.services.session_compactor.get_settings") as mock_settings, \
             patch("app.services.subtopic_weights.validate_subtopic_updates", side_effect=fake_validate):
            mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
            result = await _call_summarization_llm(sample_messages, "Graphs")

        # Only the valid one should remain
        assert result["skill_updates"] is not None
        assert len(result["skill_updates"]) == 1
        assert result["skill_updates"][0].subtopic == "recursion"

    @pytest.mark.asyncio
    async def test_wrong_tool_name_raises(self, sample_messages):
        """If tool_use block has wrong name, raises ValueError."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "wrong_tool_name"
        tool_block.input = {"summary": "test", "skill_updates": []}

        mock_response = MagicMock()
        mock_response.content = [tool_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.session_compactor.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.session_compactor.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(ValueError, match="LLM response missing compaction_result tool call"):
                    await _call_summarization_llm(sample_messages, "Graph Algorithms")


def _get_tool_schema():
    """Helper to get the tool schema for assertions."""
    from app.services.session_compactor import _COMPACTION_TOOL_SCHEMA
    return _COMPACTION_TOOL_SCHEMA
