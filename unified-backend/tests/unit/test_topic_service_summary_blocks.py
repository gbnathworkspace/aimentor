"""Unit test for the topic document's `summaryBlocks` field default
(session-narrative-summary spec, Requirement 2.2)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.topic_service import TopicService


class TestSummaryBlocksDefault:
    @pytest.mark.asyncio
    async def test_create_topic_defaults_summary_blocks_to_empty_list(self):
        service = TopicService()

        with patch("app.services.topic_service.topics_col") as mock_topics:
            mock_col = mock_topics.return_value
            mock_col.insert_one = AsyncMock()

            doc = await service.create_topic("user-1", "My Topic")

            assert doc["summaryBlocks"] == []
            inserted = mock_col.insert_one.await_args.args[0]
            assert inserted["summaryBlocks"] == []
