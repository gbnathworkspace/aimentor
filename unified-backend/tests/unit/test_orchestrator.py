"""Unit tests for orchestrator.route / route_message.

Covers:
- Rule 1 (open-topic gate) short-circuits in Python, no LLM call
- route_message parses a validated OrchestratorDecision from a mocked
  Haiku tool_use response
- Timeout/exception/malformed response fall back to tutoring_agent
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.orchestrator import AgentName, MatchedRule, route, route_message


def _tool_use_response(**kwargs) -> SimpleNamespace:
    tool_block = SimpleNamespace(type="tool_use", input=kwargs)
    return SimpleNamespace(content=[tool_block])


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.orchestrator.get_settings") as mock_get_settings:
        mock_get_settings.return_value = SimpleNamespace(ANTHROPIC_API_KEY="test-key")
        yield


class TestRule1OpenTopicGate:
    def test_topic_id_present_short_circuits_to_tutoring(self):
        decision = route("what is my progress in aws?", topic_id="t1")

        assert decision is not None
        assert decision.matched_rule == MatchedRule.RULE_1_OPEN_TOPIC_GATE
        assert decision.agent == AgentName.TUTORING

    def test_no_topic_id_defers_to_route_message(self):
        decision = route("archive my python topic", topic_id=None)

        assert decision is None


class TestRouteMessage:
    @pytest.mark.asyncio
    async def test_parses_agent_from_tool_use(self):
        with patch("app.services.orchestrator.anthropic.AsyncAnthropic"):
            with patch(
                "app.services.orchestrator.traced_messages_create",
                AsyncMock(return_value=_tool_use_response(
                    agent="command_agent", reasoning="explicit archive request",
                )),
            ):
                decision = await route_message("archive my python topic")

        assert decision.agent == AgentName.COMMAND
        assert decision.matched_rule == MatchedRule.RULE_2_MODEL_DISPATCH

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_tutoring(self):
        with patch("app.services.orchestrator.anthropic.AsyncAnthropic"):
            with patch(
                "app.services.orchestrator.asyncio.wait_for",
                AsyncMock(side_effect=TimeoutError()),
            ):
                decision = await route_message("hello")

        assert decision.agent == AgentName.TUTORING
        assert decision.matched_rule == MatchedRule.RULE_3_FALLBACK

    @pytest.mark.asyncio
    async def test_malformed_response_falls_back_to_tutoring(self):
        with patch("app.services.orchestrator.anthropic.AsyncAnthropic"):
            with patch(
                "app.services.orchestrator.traced_messages_create",
                AsyncMock(return_value=SimpleNamespace(content=[])),
            ):
                decision = await route_message("hello")

        assert decision.agent == AgentName.TUTORING
        assert decision.matched_rule == MatchedRule.RULE_3_FALLBACK

    @pytest.mark.asyncio
    async def test_api_error_falls_back_to_tutoring(self):
        with patch("app.services.orchestrator.anthropic.AsyncAnthropic"):
            with patch(
                "app.services.orchestrator.traced_messages_create",
                AsyncMock(side_effect=RuntimeError("boom")),
            ):
                decision = await route_message("hello")

        assert decision.agent == AgentName.TUTORING
        assert decision.matched_rule == MatchedRule.RULE_3_FALLBACK
