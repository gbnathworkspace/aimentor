"""Unit tests for mode_router.route_user_turn.

Tests cover:
- Rule 1 (cold start) short-circuits in Python, no LLM call
- Rules 2-6 parse a validated RouterDecision from a mocked Haiku tool_use response
- Timeout/exception/malformed response fall back to SOCRATIC
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mode_router import MatchedRule, MentorMode, route_user_turn


def _tool_use_response(**kwargs) -> SimpleNamespace:
    """Fake an Anthropic tool_use response shaped for _parse_tool_use_response."""
    tool_block = SimpleNamespace(type="tool_use", input=kwargs)
    return SimpleNamespace(content=[tool_block])


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.mode_router.get_settings") as mock_get_settings:
        mock_get_settings.return_value = SimpleNamespace(ANTHROPIC_API_KEY="test-key")
        yield


class TestRule1ColdStart:
    @pytest.mark.asyncio
    async def test_unassessed_skill_short_circuits_to_diagnostic(self):
        """No skill node at all — Rule 1 fires, no LLM call made."""
        with patch("app.services.mode_router.anthropic.AsyncAnthropic") as mock_client_cls:
            decision = await route_user_turn(query="teach me JS", skill={}, recent_messages=[])

        assert decision.matched_rule == MatchedRule.RULE_1_COLD_START
        assert decision.selected_mode == MentorMode.DIAGNOSTIC
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_last_studied_short_circuits_to_diagnostic(self):
        """Skill node exists but last_studied isn't set (never diagnosed)."""
        with patch("app.services.mode_router.anthropic.AsyncAnthropic") as mock_client_cls:
            decision = await route_user_turn(
                query="teach me JS",
                skill={"subtopic_mastery": {}},
                recent_messages=[],
            )

        assert decision.selected_mode == MentorMode.DIAGNOSTIC
        mock_client_cls.assert_not_called()


class TestRoutedRules:
    @pytest.mark.asyncio
    async def test_assessed_skill_calls_haiku_and_parses_decision(self):
        """Once last_studied is set, Rule 1 doesn't fire — a real router call happens."""
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(
                matched_rule="RULE_2_URGENCY_DIRECT",
                selected_mode="DIRECT",
                reasoning="User asked for exact syntax.",
                instruction_override="Answer with the array push syntax only.",
            )
        )

        with patch("app.services.mode_router.anthropic.AsyncAnthropic", return_value=fake_client):
            decision = await route_user_turn(
                query="syntax for array push in JS",
                skill={"subtopic_mastery": {"Arrays": 55}, "last_studied": "2024-01-01T00:00:00Z"},
                recent_messages=[],
            )

        assert decision.matched_rule == MatchedRule.RULE_2_URGENCY_DIRECT
        assert decision.selected_mode == MentorMode.DIRECT
        assert decision.instruction_override == "Answer with the array push syntax only."
        fake_client.messages.create.assert_called_once()
        # Forced tool_use, not free-text JSON (reliability — matches
        # compaction_service's established pattern).
        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "select_mentor_mode"}


class TestFailureFallback:
    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_socratic(self):
        import asyncio

        fake_client = MagicMock()

        async def _hang(*_a, **_kw):
            raise asyncio.TimeoutError()

        fake_client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("app.services.mode_router.anthropic.AsyncAnthropic", return_value=fake_client):
            decision = await route_user_turn(
                query="anything",
                skill={"subtopic_mastery": {"x": 1}, "last_studied": "2024-01-01T00:00:00Z"},
                recent_messages=[],
            )

        assert decision.matched_rule == MatchedRule.RULE_6_CATCH_ALL_FALLBACK
        assert decision.selected_mode == MentorMode.SOCRATIC

    @pytest.mark.asyncio
    async def test_api_exception_falls_back_to_socratic(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("app.services.mode_router.anthropic.AsyncAnthropic", return_value=fake_client):
            decision = await route_user_turn(
                query="anything", skill={"subtopic_mastery": {"x": 1}, "last_studied": "2024-01-01T00:00:00Z"}, recent_messages=[]
            )

        assert decision.selected_mode == MentorMode.SOCRATIC

    @pytest.mark.asyncio
    async def test_malformed_response_falls_back_to_socratic(self):
        """No tool_use block in the response — treated as unusable, not a crash."""
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
        )

        with patch("app.services.mode_router.anthropic.AsyncAnthropic", return_value=fake_client):
            decision = await route_user_turn(
                query="anything", skill={"subtopic_mastery": {"x": 1}, "last_studied": "2024-01-01T00:00:00Z"}, recent_messages=[]
            )

        assert decision.selected_mode == MentorMode.SOCRATIC

    @pytest.mark.asyncio
    async def test_invalid_enum_value_falls_back_to_socratic(self):
        """A response with a mode outside the 5 valid enum values doesn't crash the turn."""
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(
                matched_rule="RULE_6_CATCH_ALL_FALLBACK",
                selected_mode="NOT_A_REAL_MODE",
                reasoning="bad",
            )
        )

        with patch("app.services.mode_router.anthropic.AsyncAnthropic", return_value=fake_client):
            decision = await route_user_turn(
                query="anything", skill={"subtopic_mastery": {"x": 1}, "last_studied": "2024-01-01T00:00:00Z"}, recent_messages=[]
            )

        assert decision.selected_mode == MentorMode.SOCRATIC
