"""Unit tests for CompactionService._call_summarization_llm.

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

from app.services.compaction_service import (
    CompactionService,
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
    """Tests for _validate_skill_updates helper."""

    def test_valid_update_passes(self):
        """A well-formed skill update passes validation."""
        updates = [
            {
                "topic": "Graph Algorithms",
                "new_level": "intermediate",
                "weak_areas": ["DFS traversal"],
                "strong_areas": ["BFS basics"],
            }
        ]
        result = _validate_skill_updates(updates)
        assert len(result) == 1
        assert result[0]["topic"] == "Graph Algorithms"
        assert result[0]["new_level"] == "intermediate"

    def test_invalid_level_rejected(self):
        """Skill update with invalid level is filtered out."""
        updates = [
            {
                "topic": "Graphs",
                "new_level": "master",  # invalid
                "weak_areas": [],
                "strong_areas": [],
            }
        ]
        result = _validate_skill_updates(updates)
        assert len(result) == 0

    def test_missing_topic_rejected(self):
        """Skill update with empty topic is filtered out."""
        updates = [
            {
                "topic": "",
                "new_level": "beginner",
                "weak_areas": [],
                "strong_areas": [],
            }
        ]
        result = _validate_skill_updates(updates)
        assert len(result) == 0

    def test_non_dict_items_filtered(self):
        """Non-dict items in the list are filtered out."""
        updates = ["not a dict", 123, None]
        result = _validate_skill_updates(updates)
        assert len(result) == 0

    def test_non_list_areas_default_to_empty(self):
        """Non-list weak_areas/strong_areas default to empty lists."""
        updates = [
            {
                "topic": "Graphs",
                "new_level": "beginner",
                "weak_areas": "not a list",
                "strong_areas": None,
            }
        ]
        result = _validate_skill_updates(updates)
        assert len(result) == 1
        assert result[0]["weak_areas"] == []
        assert result[0]["strong_areas"] == []

    def test_non_string_items_in_areas_filtered(self):
        """Non-string items within area lists are filtered out."""
        updates = [
            {
                "topic": "Graphs",
                "new_level": "beginner",
                "weak_areas": ["valid", 123, None, "also valid"],
                "strong_areas": ["ok"],
            }
        ]
        result = _validate_skill_updates(updates)
        assert result[0]["weak_areas"] == ["valid", "also valid"]


class TestCallSummarizationLLM:
    """Tests for CompactionService._call_summarization_llm."""

    @pytest.fixture
    def service(self):
        """Create a CompactionService instance."""
        return CompactionService()

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
    async def test_formats_messages_into_prompt(self, service, sample_messages):
        """Messages are formatted and included in the LLM prompt."""
        mock_client = AsyncMock()
        mock_response = self._make_tool_use_response(
            "The student learned about BFS and DFS graph traversal algorithms.",
            [],
        )
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await service._call_summarization_llm(sample_messages)

        # Verify messages.create was called
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]

        # Verify the prompt contains conversation content
        prompt_content = call_kwargs["messages"][0]["content"]
        assert "USER: Can you explain BFS?" in prompt_content
        assert "ASSISTANT: BFS is a graph traversal algorithm" in prompt_content

        # Verify tool is passed
        assert call_kwargs["tools"] == [_get_tool_schema()]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "compaction_result"}

    @pytest.mark.asyncio
    async def test_parses_valid_tool_use_response(self, service, sample_messages):
        """Valid tool_use response is parsed correctly with summary and skill updates."""
        skill_updates = [
            {
                "topic": "Graph Algorithms",
                "new_level": "intermediate",
                "weak_areas": ["DFS backtracking"],
                "strong_areas": ["BFS traversal", "Queue usage"],
            }
        ]
        mock_response = self._make_tool_use_response(
            "Student explored BFS and DFS algorithms, showing good understanding of BFS queue-based traversal but struggling with DFS backtracking mechanics.",
            skill_updates,
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await service._call_summarization_llm(sample_messages)

        assert result["summary"].startswith("Student explored BFS and DFS")
        assert result["skill_updates"] is not None
        assert len(result["skill_updates"]) == 1
        assert result["skill_updates"][0]["topic"] == "Graph Algorithms"
        assert result["skill_updates"][0]["new_level"] == "intermediate"

    @pytest.mark.asyncio
    async def test_parses_taught_concepts(self, service, sample_messages):
        """taught_concepts entries are extracted, stripped, and non-strings dropped."""
        mock_response = self._make_tool_use_response(
            "Student learned BFS.",
            [],
            taught_concepts=["  BFS graph traversal  ", "", 42, "DFS backtracking"],
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await service._call_summarization_llm(sample_messages)

        assert result["taught_concepts"] == ["BFS graph traversal", "DFS backtracking"]

    @pytest.mark.asyncio
    async def test_missing_taught_concepts_defaults_empty(self, service, sample_messages):
        """Backward-compat: a response with no taught_concepts key parses to []."""
        mock_response = self._make_tool_use_response("Student learned BFS.", [])
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await service._call_summarization_llm(sample_messages)

        assert result["taught_concepts"] == []

    @pytest.mark.asyncio
    async def test_no_skill_updates_returns_none(self, service, sample_messages):
        """When LLM returns empty skill_updates array, result has None."""
        mock_response = self._make_tool_use_response(
            "Brief casual conversation about study plans without deep learning content.",
            [],
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await service._call_summarization_llm(sample_messages)

        assert result["summary"] == "Brief casual conversation about study plans without deep learning content."
        assert result["skill_updates"] is None

    @pytest.mark.asyncio
    async def test_malformed_response_no_tool_use_block_raises(self, service, sample_messages):
        """If LLM response has no tool_use block, raises ValueError."""
        # Response with only a text block, no tool_use
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Some random text"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(ValueError, match="LLM response missing compaction_result tool call"):
                    await service._call_summarization_llm(sample_messages)

    @pytest.mark.asyncio
    async def test_empty_summary_raises(self, service, sample_messages):
        """If LLM returns empty summary string, raises ValueError."""
        mock_response = self._make_tool_use_response("", [])

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(ValueError, match="LLM returned empty summary"):
                    await service._call_summarization_llm(sample_messages)

    @pytest.mark.asyncio
    async def test_timeout_raises(self, service, sample_messages):
        """LLM timeout raises asyncio.TimeoutError which propagates."""
        import asyncio

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(asyncio.TimeoutError):
                    await service._call_summarization_llm(sample_messages)

    @pytest.mark.asyncio
    async def test_invalid_skill_updates_filtered(self, service, sample_messages):
        """Invalid skill updates in response are filtered out; valid ones kept."""
        skill_updates = [
            {
                "topic": "Graphs",
                "new_level": "intermediate",
                "gap": 40,
                "weak_areas": ["recursion"],
                "strong_areas": ["iteration"],
            },
            {
                "topic": "Invalid",
                "new_level": "master",  # invalid level
                "gap": 50,
                "weak_areas": [],
                "strong_areas": [],
            },
        ]
        mock_response = self._make_tool_use_response(
            "Learning about graph algorithms.", skill_updates
        )
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                result = await service._call_summarization_llm(sample_messages)

        # Only the valid one should remain
        assert result["skill_updates"] is not None
        assert len(result["skill_updates"]) == 1
        assert result["skill_updates"][0]["topic"] == "Graphs"

    @pytest.mark.asyncio
    async def test_wrong_tool_name_raises(self, service, sample_messages):
        """If tool_use block has wrong name, raises ValueError."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "wrong_tool_name"
        tool_block.input = {"summary": "test", "skill_updates": []}

        mock_response = MagicMock()
        mock_response.content = [tool_block]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("app.services.compaction_service.anthropic.AsyncAnthropic", return_value=mock_client):
            with patch("app.services.compaction_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
                with pytest.raises(ValueError, match="LLM response missing compaction_result tool call"):
                    await service._call_summarization_llm(sample_messages)


def _get_tool_schema():
    """Helper to get the tool schema for assertions."""
    from app.services.compaction_service import _COMPACTION_TOOL_SCHEMA
    return _COMPACTION_TOOL_SCHEMA
