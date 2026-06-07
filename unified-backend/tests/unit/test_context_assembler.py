"""Unit tests for app/services/context_assembler.py — context assembly logic."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services.context_assembler import assemble, _vector_search


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
                "app.services.context_assembler._vector_search",
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
                "app.services.context_assembler._vector_search",
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
                "app.services.context_assembler._vector_search",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(return_value=None)

            result = await assemble("u1", "topic", "query")

        assert result["skill"] == {}


class TestVectorSearch:
    """Verify _vector_search graceful degradation."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_embed_failure(self):
        """If embed_text returns empty vector, return empty list."""
        with patch(
            "app.services.context_assembler.embed_text",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _vector_search("u1", "query", "topic", limit=3)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        """If vector search pipeline raises, return empty list."""
        with patch(
            "app.services.context_assembler.embed_text",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            result = await _vector_search("u1", "query", "topic", limit=3)

        assert result == []

    @pytest.mark.asyncio
    async def test_successful_search_returns_results(self):
        """Happy path: embedding + aggregation pipeline returns results."""
        mock_vector = [0.1] * 128
        mock_results = [
            {"session_id": "s1", "title": "Session 1", "score": 0.95},
            {"session_id": "s2", "title": "Session 2", "score": 0.87},
        ]

        # Create a mock cursor that has to_list
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_results)

        with (
            patch(
                "app.services.context_assembler.embed_text",
                new_callable=AsyncMock,
                return_value=mock_vector,
            ),
            patch(
                "app.services.context_assembler.sessions_col"
            ) as mock_sessions,
        ):
            mock_sessions.return_value.aggregate = lambda pipeline: mock_cursor

            result = await _vector_search("u1", "What is a matrix?", "linear-algebra", limit=3)

        assert result == mock_results
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_without_topic_omits_topic_filter(self):
        """When topic is None, the filter should not include topic."""
        mock_vector = [0.1] * 128
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        captured_pipeline = []

        def capture_aggregate(pipeline):
            captured_pipeline.extend(pipeline)
            return mock_cursor

        with (
            patch(
                "app.services.context_assembler.embed_text",
                new_callable=AsyncMock,
                return_value=mock_vector,
            ),
            patch(
                "app.services.context_assembler.sessions_col"
            ) as mock_sessions,
        ):
            mock_sessions.return_value.aggregate = capture_aggregate

            await _vector_search("u1", "query", None, limit=3)

        # Check the $vectorSearch filter does not contain topic
        vector_search_stage = captured_pipeline[0]["$vectorSearch"]
        assert "topic" not in vector_search_stage["filter"]
