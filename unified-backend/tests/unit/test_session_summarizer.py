"""Unit tests for session_summarizer.py — close_session and enforce_word_cap.

Requirements: 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import session_summarizer as ss


def _msg(msg_id: str, ts: datetime) -> dict:
    return {"type": "message", "id": msg_id, "role": "user", "content": "hi", "timestamp": ts}


def _block(block_id: str, source_ids: list[str], word_count: int, created_at: datetime, merge_depth: int = 0) -> dict:
    return {
        "blockId": block_id,
        "sourceSessionIds": source_ids,
        "text": "word " * word_count,
        "wordCount": word_count,
        "mergeDepth": merge_depth,
        "createdAt": created_at,
        "lastMergedAt": created_at,
    }


class TestCloseSession:
    @pytest.mark.asyncio
    async def test_noop_when_no_uncovered_messages(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        topic_doc = {
            "topicId": "t1", "userId": "u1", "version": 0,
            "summaryBlocks": [_block("b1", ["m1"], 100, ts)],
            "messages": [_msg("m1", ts)],
        }

        with patch("app.services.session_summarizer.topics_col") as mock_topics, \
             patch.object(ss._compaction_service, "_call_summarization_llm", new=AsyncMock()) as mock_llm:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await ss.close_session("t1", "u1", upto_timestamp=ts)

            mock_llm.assert_not_called()
            mock_col.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_fresh_block_created_with_correct_fields(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        topic_doc = {
            "topicId": "t1", "userId": "u1", "version": 0,
            "summaryBlocks": [],
            "messages": [_msg("m1", ts)],
        }

        with patch("app.services.session_summarizer.topics_col") as mock_topics, \
             patch.object(
                 ss._compaction_service, "_call_summarization_llm",
                 new=AsyncMock(return_value={"summary": "did stuff", "skill_updates": None, "taught_concepts": []}),
             ), \
             patch.object(ss._compaction_service, "_apply_skill_updates", new=AsyncMock()) as mock_skills, \
             patch.object(ss._compaction_service, "_apply_taught_concepts", new=AsyncMock()) as mock_concepts:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
            mock_topics.return_value = mock_col

            await ss.close_session("t1", "u1", upto_timestamp=ts)

            mock_skills.assert_not_called()
            mock_concepts.assert_not_called()
            assert mock_col.update_one.await_count == 1
            new_blocks = mock_col.update_one.await_args.args[1]["$set"]["summaryBlocks"]
            assert len(new_blocks) == 1
            assert new_blocks[0]["sourceSessionIds"] == ["m1"]
            assert new_blocks[0]["mergeDepth"] == 0
            assert new_blocks[0]["text"] == "did stuff"

    @pytest.mark.asyncio
    async def test_llm_failure_leaves_messages_uncovered(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        topic_doc = {
            "topicId": "t1", "userId": "u1", "version": 0,
            "summaryBlocks": [],
            "messages": [_msg("m1", ts)],
        }

        with patch("app.services.session_summarizer.topics_col") as mock_topics, \
             patch.object(
                 ss._compaction_service, "_call_summarization_llm",
                 new=AsyncMock(side_effect=RuntimeError("boom")),
             ):
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await ss.close_session("t1", "u1", upto_timestamp=ts)

            mock_col.update_one.assert_not_called()


class TestEnforceWordCap:
    @pytest.mark.asyncio
    async def test_under_cap_no_merge(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block("b1", ["m1"], 100, ts)]

        with patch("app.services.session_summarizer._call_merge_two_blocks_llm", new=AsyncMock()) as mock_merge:
            result = await ss.enforce_word_cap(blocks)

            mock_merge.assert_not_called()
            assert result == blocks

    @pytest.mark.asyncio
    async def test_over_cap_merges_oldest_pair(self):
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        blocks = [_block("b1", ["m1"], 300, t1), _block("b2", ["m2"], 300, t2)]

        with patch(
            "app.services.session_summarizer._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 200),
        ) as mock_merge:
            result = await ss.enforce_word_cap(blocks)

            mock_merge.assert_awaited_once()
            assert len(result) == 1
            assert result[0]["sourceSessionIds"] == ["m1", "m2"]
            assert result[0]["mergeDepth"] == 1
            assert result[0]["createdAt"] == t1

    @pytest.mark.asyncio
    async def test_stops_after_max_merge_passes(self):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block(f"b{i}", [f"m{i}"], 300, base) for i in range(8)]

        with patch(
            "app.services.session_summarizer._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 250),
        ) as mock_merge:
            result = await ss.enforce_word_cap(blocks)

            assert mock_merge.await_count == ss.MAX_MERGE_PASSES_PER_CLOSE
            # 8 blocks - 3 merges (each merge removes 1 net block) = 5
            assert len(result) == 8 - ss.MAX_MERGE_PASSES_PER_CLOSE

    @pytest.mark.asyncio
    async def test_odd_block_left_unpaired(self):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block(f"b{i}", [f"m{i}"], 300, base) for i in range(3)]

        with patch(
            "app.services.session_summarizer._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 200),
        ):
            result = await ss.enforce_word_cap(blocks)

            # 3 blocks (900 words) -> merge two oldest into 200 words -> 2
            # blocks totalling 500, at cap, loop stops; the odd one (b2) is
            # left untouched rather than special-cased (Requirement 3.6)
            assert len(result) == 2
            block_ids = {b["blockId"] for b in result}
            assert "b2" in block_ids

    @pytest.mark.asyncio
    async def test_merge_failure_keeps_prior_blocks(self):
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        blocks = [_block("b1", ["m1"], 300, t1), _block("b2", ["m2"], 300, t2)]

        with patch(
            "app.services.session_summarizer._call_merge_two_blocks_llm",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await ss.enforce_word_cap(blocks)

            assert result == blocks

    def test_word_count(self):
        assert ss._word_count("one two three") == 3
        assert ss._word_count("") == 0


class TestNoDoubleSummarization:
    """Property: the union of sourceSessionIds across all blocks never
    contains a duplicate message ID, before or after any sequence of merges
    (Property 1, Requirements 2.4, 3.3)."""

    @pytest.mark.asyncio
    async def test_source_ids_stay_unique_across_repeated_merges(self):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block(f"b{i}", [f"m{i}"], 300, base) for i in range(6)]

        def _merge_id_count(before: list[dict]) -> int:
            return sum(len(b["sourceSessionIds"]) for b in before)

        total_ids_before = _merge_id_count(blocks)

        with patch(
            "app.services.session_summarizer._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 200),
        ):
            result = await ss.enforce_word_cap(blocks)

        all_ids = [mid for b in result for mid in b["sourceSessionIds"]]
        assert len(all_ids) == len(set(all_ids))
        assert len(all_ids) == total_ids_before
