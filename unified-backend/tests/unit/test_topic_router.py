"""Unit tests for topic_router.route_topic.

Tests cover:
- No candidate topics short-circuits to an empty result, no LLM call
- MATCH parses a single topic_id from a mocked Haiku tool_use response
- AMBIGUOUS parses up to 4 related_ids, filtered to known ids
- NEW, and a malformed/out-of-enum decision, both fall back to empty
- Timeout/exception/malformed response fall back to empty (fail-open)
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.topic_router import route_topic


def _tool_use_response(**kwargs) -> SimpleNamespace:
    tool_block = SimpleNamespace(type="tool_use", input=kwargs)
    return SimpleNamespace(content=[tool_block])


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.topic_router.get_settings") as mock_get_settings:
        mock_get_settings.return_value = SimpleNamespace(ANTHROPIC_API_KEY="test-key")
        yield


TOPICS = [
    {"topicId": "t1", "title": "React", "subject": "Frontend"},
    {"topicId": "t2", "title": "SQL Basics", "subject": ""},
    {"topicId": "t3", "title": "Vue", "subject": "Frontend"},
]


class TestNoCandidates:
    @pytest.mark.asyncio
    async def test_empty_topics_short_circuits_to_empty_result(self):
        with patch("app.services.topic_router.anthropic.AsyncAnthropic") as mock_client_cls:
            result = await route_topic("explain hooks", [])

        assert result.topic_id is None
        assert result.related_ids == []
        mock_client_cls.assert_not_called()


class TestMatch:
    @pytest.mark.asyncio
    async def test_matched_topic_id_returned(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(
                decision="MATCH", topic_id="t1", reasoning="Both about React hooks.",
            )
        )

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("explain useEffect", TOPICS)

        assert result.topic_id == "t1"
        assert result.related_ids == []
        fake_client.messages.create.assert_called_once()
        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "select_topic"}

    @pytest.mark.asyncio
    async def test_match_with_out_of_enum_id_falls_back_to_empty(self):
        """Model hallucinating an id outside the given set never leaks
        through as a topicId — treated as an unusable decision."""
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(decision="MATCH", topic_id="not-a-real-id", reasoning="oops")
        )

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("anything", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == []


class TestAmbiguous:
    @pytest.mark.asyncio
    async def test_related_ids_returned_filtered_and_capped(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(
                decision="AMBIGUOUS",
                # includes a bogus id that must be dropped, and would need
                # capping at 4 if the model over-returned
                related_ids=["t1", "bogus-id", "t3"],
                reasoning="Both React and Vue frontend topics could fit.",
            )
        )

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("explain component state", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == ["t1", "t3"]

    @pytest.mark.asyncio
    async def test_ambiguous_with_no_valid_ids_falls_back_to_empty(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(decision="AMBIGUOUS", related_ids=[], reasoning="nothing solid")
        )

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("anything", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == []


class TestNewAndFailureFallback:
    @pytest.mark.asyncio
    async def test_new_resolves_to_empty_result(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=_tool_use_response(decision="NEW", reasoning="Unrelated subject.")
        )

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("plan a wedding", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == []

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_empty(self):
        import asyncio

        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("anything", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == []

    @pytest.mark.asyncio
    async def test_api_exception_falls_back_to_empty(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("anything", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == []

    @pytest.mark.asyncio
    async def test_malformed_response_falls_back_to_empty(self):
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
        )

        with patch("app.services.topic_router.anthropic.AsyncAnthropic", return_value=fake_client):
            result = await route_topic("anything", TOPICS)

        assert result.topic_id is None
        assert result.related_ids == []
