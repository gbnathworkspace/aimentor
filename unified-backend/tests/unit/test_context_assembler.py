"""Unit tests for app/services/context_assembler.py — context assembly logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.context_assembler import assemble, _recent_episodes, _recent_topic_summaries


class TestAssemble:
    """Verify assemble() gathers L1, L2, L3 with graceful degradation."""

    @pytest.mark.asyncio
    async def test_returns_profile_skill_episodes(self):
        """Happy path: all three layers return data."""
        mock_profile = {"user_id": "u1", "goal": "Learn ML", "deadline": "2025-06"}
        mock_skill = {"user_id": "u1", "topic": "linear-algebra", "current_level": "beginner"}
        mock_episodes = [{"session_id": "s1", "title": "Session 1", "score": 0.9}]

        with (
            patch(
                "app.services.context_assembler.profiles_col"
            ) as mock_profiles,
            patch(
                "app.services.context_assembler.skill_graph_col"
            ) as mock_skills,
            patch(
                "app.services.context_assembler._recent_episodes",
                new_callable=AsyncMock,
                return_value=mock_episodes,
            ),
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(return_value=mock_skill)

            result = await assemble("u1", "linear-algebra", "What is a matrix?")

        assert result["profile"] == mock_profile
        assert result["skill"] == mock_skill
        assert result["episodes"] == mock_episodes

    @pytest.mark.asyncio
    async def test_raises_400_when_no_profile(self):
        """If L1 profile is missing, raise HTTP 400."""
        with patch(
            "app.services.context_assembler.profiles_col"
        ) as mock_profiles:
            mock_profiles.return_value.find_one = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await assemble("u1", "topic", "query")

        assert exc_info.value.status_code == 400
        assert "onboarding" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_skill_failure_returns_empty_dict(self):
        """If L2 skill fetch raises, degrade to empty dict."""
        mock_profile = {"user_id": "u1", "goal": "Learn ML"}

        with (
            patch(
                "app.services.context_assembler.profiles_col"
            ) as mock_profiles,
            patch(
                "app.services.context_assembler.skill_graph_col"
            ) as mock_skills,
            patch(
                "app.services.context_assembler._recent_episodes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(
                side_effect=Exception("DB connection lost")
            )

            result = await assemble("u1", "topic", "query")

        assert result["profile"] == mock_profile
        assert result["skill"] == {}
        assert result["episodes"] == []

    @pytest.mark.asyncio
    async def test_skill_none_returns_empty_dict(self):
        """If L2 skill node is None (not found), return empty dict."""
        mock_profile = {"user_id": "u1", "goal": "Learn ML"}

        with (
            patch(
                "app.services.context_assembler.profiles_col"
            ) as mock_profiles,
            patch(
                "app.services.context_assembler.skill_graph_col"
            ) as mock_skills,
            patch(
                "app.services.context_assembler._recent_episodes",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(return_value=None)

            result = await assemble("u1", "topic", "query")

        assert result["skill"] == {}


def _mock_sessions_returning(docs):
    """Build a mock sessions_col whose find().sort().limit().to_list() yields docs."""
    cursor = MagicMock()
    cursor.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=docs)
    col = MagicMock()
    col.find.return_value = cursor
    return col


class TestRecentEpisodes:
    """Verify _recent_episodes recency fetch + graceful degradation (issue #5 deferral)."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        """If the query raises, return empty list so the mentor still responds."""
        col = MagicMock()
        col.find.side_effect = Exception("DB down")
        with patch("app.services.context_assembler.sessions_col", return_value=col):
            result = await _recent_episodes("u1", "topic", limit=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_prefers_same_topic_then_recent(self):
        """Same-topic sessions come first, then other recent ones; limit respected."""
        docs = [
            {"session_id": "s3", "topic": "Trees", "summary": "newest other"},
            {"session_id": "s2", "topic": "Graphs", "summary": "mid same"},
            {"session_id": "s1", "topic": "Graphs", "summary": "old same"},
        ]
        col = _mock_sessions_returning(docs)
        with patch("app.services.context_assembler.sessions_col", return_value=col):
            result = await _recent_episodes("u1", "Graphs", limit=2)
        assert [d["topic"] for d in result] == ["Graphs", "Graphs"]
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_query_filters_ended_with_summary(self):
        """Only ended sessions with a non-empty summary are eligible."""
        col = _mock_sessions_returning([])
        with patch("app.services.context_assembler.sessions_col", return_value=col):
            await _recent_episodes("u1", None, limit=3)
        query = col.find.call_args.args[0]
        assert query["user_id"] == "u1"
        assert query["status"] == "ended"
        assert query["summary"] == {"$nin": [None, ""]}


def _mock_topics_returning(docs):
    """Build a mock topics_col whose aggregate().to_list() yields docs."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    col = MagicMock()
    col.aggregate.return_value = cursor
    return col


class TestRecentTopicSummaries:
    """Verify _recent_topic_summaries reads the topic's rolling summary from
    topics_col (issue #40, #23). Under the rolling-topic-summary model at most
    one summary entry exists per topic, so this returns 0 or 1 items scoped to
    the current topic only — no limit, no cross-topic fill (see
    .kiro/specs/rolling-topic-summary)."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        """If the query raises, return empty list so the mentor still responds."""
        col = MagicMock()
        col.aggregate.side_effect = Exception("DB down")
        with patch("app.services.context_assembler.topics_col", return_value=col):
            result = await _recent_topic_summaries("u1", "Graphs")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_topic_is_none(self):
        """No current topic means nothing to scope the query to — return []."""
        result = await _recent_topic_summaries("u1", None)
        assert result == []

    @pytest.mark.asyncio
    async def test_extracts_the_topics_rolling_summary(self):
        """The current topic's single summary block is returned."""
        docs = [
            {
                "title": "Graphs",
                "summaryBlocks": [
                    {
                        "summary": "Covered BFS and DFS",
                        "compactedRange": {"to": "2024-01-10T12:00:00Z"},
                    }
                ],
            },
        ]
        col = _mock_topics_returning(docs)
        with patch("app.services.context_assembler.topics_col", return_value=col):
            result = await _recent_topic_summaries("u1", "Graphs")
        assert len(result) == 1
        assert result[0]["topic"] == "Graphs"
        assert result[0]["summary"] == "Covered BFS and DFS"

    @pytest.mark.asyncio
    async def test_returns_empty_when_topic_has_no_summary_yet(self):
        """A topic that hasn't compacted yet has no summary blocks — empty list."""
        docs = [{"title": "Graphs", "summaryBlocks": []}]
        col = _mock_topics_returning(docs)
        with patch("app.services.context_assembler.topics_col", return_value=col):
            result = await _recent_topic_summaries("u1", "Graphs")
        assert result == []
