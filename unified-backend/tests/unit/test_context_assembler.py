"""Unit tests for app/services/context_assembler.py — context assembly logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.context_assembler import _fetch_documents, assemble


class TestAssemble:
    """Verify assemble() gathers L1, L2 with graceful degradation."""

    @pytest.mark.asyncio
    async def test_returns_profile_and_skill(self):
        """Happy path: profile and skill layers return data."""
        mock_profile = {"user_id": "u1", "goal": "Learn ML", "deadline": "2025-06"}
        mock_skill = {"user_id": "u1", "topic": "linear-algebra", "current_level": "beginner"}

        with (
            patch(
                "app.services.context_assembler.profiles_col"
            ) as mock_profiles,
            patch(
                "app.services.context_assembler.skill_graph_col"
            ) as mock_skills,
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(return_value=mock_skill)
            mock_skills.return_value.find.return_value.to_list = AsyncMock(return_value=[])

            result = await assemble("u1", "linear-algebra", "What is a matrix?")

        assert result["profile"] == mock_profile
        assert result["skill"] == mock_skill

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
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(
                side_effect=Exception("DB connection lost")
            )
            mock_skills.return_value.find.return_value.to_list = AsyncMock(return_value=[])

            result = await assemble("u1", "topic", "query")

        assert result["profile"] == mock_profile
        assert result["skill"] == {}

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
        ):
            mock_profiles.return_value.find_one = AsyncMock(return_value=mock_profile)
            mock_skills.return_value.find_one = AsyncMock(return_value=None)
            mock_skills.return_value.find.return_value.to_list = AsyncMock(return_value=[])

            result = await assemble("u1", "topic", "query")

        assert result["skill"] == {}


class TestFetchDocuments:
    """Topic-scoped documents take priority; the rest of the budget is
    filled with the user's user-wide ingested chunks."""

    @pytest.mark.asyncio
    async def test_no_topic_id_returns_only_general_documents(self):
        general = [{"text": "resume chunk"}]
        with patch("app.services.context_assembler.embeddings_col") as mock_col:
            mock_col.return_value.find.return_value.limit.return_value.to_list = AsyncMock(
                return_value=general
            )
            result = await _fetch_documents("u1", topic_id=None, limit=12)

        assert result == general

    @pytest.mark.asyncio
    async def test_topic_documents_come_first_and_cap_the_remaining_budget(self):
        topic_docs = [{"text": "topic note"}]
        general = [{"text": "resume chunk"}]

        with patch("app.services.context_assembler.embeddings_col") as mock_col:
            def find_side_effect(filter_clause, *_a, **_kw):
                cursor = MagicMock()
                if filter_clause.get("metadata.source") == "topic_document":
                    cursor.to_list = AsyncMock(return_value=topic_docs)
                else:
                    cursor.limit.return_value.to_list = AsyncMock(return_value=general)
                return cursor

            mock_col.return_value.find.side_effect = find_side_effect

            result = await _fetch_documents("u1", topic_id="topic-abc", limit=12)

        assert result == topic_docs + general

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty_list(self):
        with patch("app.services.context_assembler.embeddings_col") as mock_col:
            mock_col.return_value.find.side_effect = Exception("DB down")
            result = await _fetch_documents("u1", topic_id="topic-abc")

        assert result == []
