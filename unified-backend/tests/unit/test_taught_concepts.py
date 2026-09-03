"""Unit tests for session_compactor._apply_taught_concepts — the in-topic
record of specific things taught (TS-1: episodic memory should say what was
previously taught in a topic).
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("VOYAGE_API_KEY", "voy-test")

from app.services.session_compactor import MAX_TAUGHT_CONCEPTS, _apply_taught_concepts


class TestApplyTaughtConcepts:
    @pytest.mark.asyncio
    async def test_appends_new_concepts_to_empty_list(self):
        with patch("app.services.session_compactor.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_topics.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value={"taughtConcepts": []})
            mock_col.update_one = AsyncMock()

            await _apply_taught_concepts("topic-1", "user-1", ["Signed URLs in CloudFront"])

        mock_col.update_one.assert_called_once_with(
            {"topicId": "topic-1", "userId": "user-1"},
            {"$set": {"taughtConcepts": ["Signed URLs in CloudFront"]}},
        )

    @pytest.mark.asyncio
    async def test_deduplicates_against_existing(self):
        with patch("app.services.session_compactor.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_topics.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value={"taughtConcepts": ["Signed URLs in CloudFront"]})
            mock_col.update_one = AsyncMock()

            await _apply_taught_concepts(
                "topic-1", "user-1", ["Signed URLs in CloudFront", "Signed Cookies in CloudFront"],
            )

        set_call = mock_col.update_one.call_args[0][1]["$set"]
        assert set_call["taughtConcepts"] == ["Signed URLs in CloudFront", "Signed Cookies in CloudFront"]

    @pytest.mark.asyncio
    async def test_caps_at_max_dropping_oldest(self):
        existing = [f"concept-{i}" for i in range(MAX_TAUGHT_CONCEPTS)]
        with patch("app.services.session_compactor.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_topics.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value={"taughtConcepts": existing})
            mock_col.update_one = AsyncMock()

            await _apply_taught_concepts("topic-1", "user-1", ["newest-concept"])

        set_call = mock_col.update_one.call_args[0][1]["$set"]
        result = set_call["taughtConcepts"]
        assert len(result) == MAX_TAUGHT_CONCEPTS
        assert result[-1] == "newest-concept"
        assert "concept-0" not in result  # oldest dropped

    @pytest.mark.asyncio
    async def test_missing_topic_is_a_noop(self):
        with patch("app.services.session_compactor.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_topics.return_value = mock_col
            mock_col.find_one = AsyncMock(return_value=None)
            mock_col.update_one = AsyncMock()

            await _apply_taught_concepts("topic-1", "user-1", ["x"])

        mock_col.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self):
        """Best-effort — never raises out of the post-turn hook."""
        with patch("app.services.session_compactor.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_topics.return_value = mock_col
            mock_col.find_one = AsyncMock(side_effect=RuntimeError("db down"))

            await _apply_taught_concepts("topic-1", "user-1", ["x"])  # must not raise
