"""Unit tests for CompactionService._apply_taught_concepts — the skill_graph
record of specific things taught (TS-1: episodic memory should say what was
previously taught in a topic).
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VOYAGE_API_KEY", "voy-test")

from app.services.compaction_service import MAX_TAUGHT_CONCEPTS, CompactionService


@pytest.fixture
def service():
    return CompactionService()


class TestApplyTaughtConcepts:
    @pytest.mark.asyncio
    async def test_appends_new_concepts_to_empty_list(self, service):
        with patch("app.services.compaction_service.skill_graph_col") as mock_skill_graph:
            mock_col = MagicMock()
            mock_skill_graph.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value={"taught_concepts": []})
            mock_col.update_one = AsyncMock()

            await service._apply_taught_concepts("Topic 1", "user-1", ["Signed URLs in CloudFront"])

        mock_col.update_one.assert_called_once_with(
            {"user_id": "user-1", "topic": "Topic 1"},
            {"$set": {"taught_concepts": ["Signed URLs in CloudFront"]}},
            upsert=True,
        )

    @pytest.mark.asyncio
    async def test_deduplicates_against_existing(self, service):
        with patch("app.services.compaction_service.skill_graph_col") as mock_skill_graph:
            mock_col = MagicMock()
            mock_skill_graph.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value={"taught_concepts": ["Signed URLs in CloudFront"]})
            mock_col.update_one = AsyncMock()

            await service._apply_taught_concepts(
                "Topic 1", "user-1", ["Signed URLs in CloudFront", "Signed Cookies in CloudFront"],
            )

        set_call = mock_col.update_one.call_args[0][1]["$set"]
        assert set_call["taught_concepts"] == ["Signed URLs in CloudFront", "Signed Cookies in CloudFront"]

    @pytest.mark.asyncio
    async def test_caps_at_max_dropping_oldest(self, service):
        existing = [f"concept-{i}" for i in range(MAX_TAUGHT_CONCEPTS)]
        with patch("app.services.compaction_service.skill_graph_col") as mock_skill_graph:
            mock_col = MagicMock()
            mock_skill_graph.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value={"taught_concepts": existing})
            mock_col.update_one = AsyncMock()

            await service._apply_taught_concepts("Topic 1", "user-1", ["newest-concept"])

        set_call = mock_col.update_one.call_args[0][1]["$set"]
        result = set_call["taught_concepts"]
        assert len(result) == MAX_TAUGHT_CONCEPTS
        assert result[-1] == "newest-concept"
        assert "concept-0" not in result  # oldest dropped

    @pytest.mark.asyncio
    async def test_no_existing_skill_graph_doc_upserts(self, service):
        """No skill_graph node exists yet for this (user, topic) — the write
        still lands, creating one, rather than being skipped."""
        with patch("app.services.compaction_service.skill_graph_col") as mock_skill_graph:
            mock_col = MagicMock()
            mock_skill_graph.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value=None)
            mock_col.update_one = AsyncMock()

            await service._apply_taught_concepts("Topic 1", "user-1", ["x"])

        mock_col.update_one.assert_called_once_with(
            {"user_id": "user-1", "topic": "Topic 1"},
            {"$set": {"taught_concepts": ["x"]}},
            upsert=True,
        )

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self, service):
        """Best-effort — never raises out of the post-turn hook."""
        with patch("app.services.compaction_service.skill_graph_col") as mock_skill_graph:
            mock_col = MagicMock()
            mock_skill_graph.return_value = mock_col
            mock_col.find_one = AsyncMock(side_effect=RuntimeError("db down"))

            await service._apply_taught_concepts("Topic 1", "user-1", ["x"])  # must not raise
