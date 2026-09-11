"""Unit tests for command_agent.resolve_command / execute_command.

Covers:
- No topics -> NONE, no LLM call
- A parsed DELETE/ARCHIVE/RENAME decision from a mocked Haiku tool_use response
- Timeout/exception/malformed response fall back to NONE
- execute_command dispatches to the right TopicService method
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.command_agent import (
    CommandAction,
    CommandDecision,
    execute_command,
    resolve_command,
)

_TOPICS = [{"topicId": "t1", "title": "Python"}, {"topicId": "t2", "title": "AWS"}]


def _tool_use_response(**kwargs) -> SimpleNamespace:
    tool_block = SimpleNamespace(type="tool_use", input=kwargs)
    return SimpleNamespace(content=[tool_block])


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.command_agent.get_settings") as mock_get_settings:
        mock_get_settings.return_value = SimpleNamespace(ANTHROPIC_API_KEY="test-key")
        yield


class TestResolveCommand:
    @pytest.mark.asyncio
    async def test_no_topics_short_circuits_to_none(self):
        with patch("app.services.command_agent.anthropic.AsyncAnthropic") as mock_client_cls:
            decision = await resolve_command("archive my python topic", [])

        assert decision.action == CommandAction.NONE
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_archive_parses_from_tool_use(self):
        with patch("app.services.command_agent.anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            with patch(
                "app.services.command_agent.traced_messages_create",
                AsyncMock(return_value=_tool_use_response(
                    action="ARCHIVE", topic_id="t1", reasoning="matches Python",
                )),
            ):
                decision = await resolve_command("archive my python topic", _TOPICS)

        assert decision.action == CommandAction.ARCHIVE
        assert decision.topic_id == "t1"

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_none(self):
        with patch("app.services.command_agent.anthropic.AsyncAnthropic"):
            with patch(
                "app.services.command_agent.asyncio.wait_for",
                AsyncMock(side_effect=TimeoutError()),
            ):
                decision = await resolve_command("archive something", _TOPICS)

        assert decision.action == CommandAction.NONE

    @pytest.mark.asyncio
    async def test_malformed_response_falls_back_to_none(self):
        with patch("app.services.command_agent.anthropic.AsyncAnthropic"):
            with patch(
                "app.services.command_agent.traced_messages_create",
                AsyncMock(return_value=SimpleNamespace(content=[])),
            ):
                decision = await resolve_command("archive something", _TOPICS)

        assert decision.action == CommandAction.NONE


class TestExecuteCommand:
    @pytest.mark.asyncio
    async def test_none_action_is_a_noop(self):
        result = await execute_command(CommandDecision(action=CommandAction.NONE), "user1")
        assert result["status"] == "no_action"

    @pytest.mark.asyncio
    async def test_archive_calls_topic_service_archive(self):
        with patch(
            "app.services.command_agent._topic_service.archive_topic", AsyncMock()
        ) as mock_archive:
            result = await execute_command(
                CommandDecision(action=CommandAction.ARCHIVE, topic_id="t1"), "user1"
            )

        mock_archive.assert_awaited_once_with("t1", "user1")
        assert result == {"status": "archived", "topic_id": "t1"}

    @pytest.mark.asyncio
    async def test_rename_without_new_title_is_a_noop(self):
        result = await execute_command(
            CommandDecision(action=CommandAction.RENAME, topic_id="t1"), "user1"
        )
        assert result["status"] == "no_action"

    @pytest.mark.asyncio
    async def test_rename_calls_topic_service_update(self):
        with patch(
            "app.services.command_agent._topic_service.update_topic",
            AsyncMock(return_value={"title": "New Title"}),
        ) as mock_update:
            result = await execute_command(
                CommandDecision(action=CommandAction.RENAME, topic_id="t1", new_title="New Title"),
                "user1",
            )

        mock_update.assert_awaited_once_with("t1", "user1", title="New Title")
        assert result == {"status": "renamed", "topic_id": "t1", "title": "New Title"}
