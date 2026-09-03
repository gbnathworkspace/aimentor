"""Unit tests for session_compactor.py — close_session (including the
message-pruning step) and enforce_word_cap.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import session_compactor as sc


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

        with patch("app.services.session_compactor.topics_col") as mock_topics, \
             patch.object(sc, "_call_summarization_llm", new=AsyncMock()) as mock_llm:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await sc.close_session("t1", "u1", upto_timestamp=ts)

            mock_llm.assert_not_called()
            mock_col.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_fresh_block_created_and_covered_messages_pruned(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        topic_doc = {
            "topicId": "t1", "userId": "u1", "version": 0,
            "summaryBlocks": [],
            "messages": [_msg("m1", ts)],
        }

        with patch("app.services.session_compactor.topics_col") as mock_topics, \
             patch("app.services.session_compactor.compaction_events_col") as mock_events, \
             patch.object(
                 sc, "_call_summarization_llm",
                 new=AsyncMock(return_value={"summary": "did stuff", "skill_updates": None, "taught_concepts": [], "profile_signals": []}),
             ), \
             patch.object(sc, "_apply_skill_updates", new=AsyncMock()) as mock_skills, \
             patch.object(sc, "_apply_taught_concepts", new=AsyncMock()) as mock_concepts, \
             patch.object(sc, "_sync_block_embeddings", new=AsyncMock()):
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
            mock_topics.return_value = mock_col
            mock_events_col = MagicMock()
            mock_events_col.insert_one = AsyncMock()
            mock_events.return_value = mock_events_col

            await sc.close_session("t1", "u1", upto_timestamp=ts)

            mock_skills.assert_not_called()
            mock_concepts.assert_not_called()
            assert mock_col.update_one.await_count == 1
            set_fields = mock_col.update_one.await_args.args[1]["$set"]
            new_blocks = set_fields["summaryBlocks"]
            assert len(new_blocks) == 1
            assert new_blocks[0]["sourceSessionIds"] == ["m1"]
            assert new_blocks[0]["mergeDepth"] == 0
            assert new_blocks[0]["text"] == "did stuff"

            # The covered raw message is pruned out of messages, reclaiming
            # its tokens — the behavior the old session_summarizer never had.
            assert set_fields["messages"] == []
            mock_events_col.insert_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_leaves_messages_uncovered(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        topic_doc = {
            "topicId": "t1", "userId": "u1", "version": 0,
            "summaryBlocks": [],
            "messages": [_msg("m1", ts)],
        }

        with patch("app.services.session_compactor.topics_col") as mock_topics, \
             patch.object(
                 sc, "_call_summarization_llm",
                 new=AsyncMock(side_effect=RuntimeError("boom")),
             ):
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await sc.close_session("t1", "u1", upto_timestamp=ts)

            mock_col.update_one.assert_not_called()


class TestEnforceWordCap:
    @pytest.mark.asyncio
    async def test_under_cap_no_merge(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block("b1", ["m1"], 100, ts)]

        with patch("app.services.session_compactor._call_merge_two_blocks_llm", new=AsyncMock()) as mock_merge:
            result = await sc.enforce_word_cap(blocks)

            mock_merge.assert_not_called()
            assert result == blocks

    @pytest.mark.asyncio
    async def test_over_cap_merges_oldest_pair(self):
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        blocks = [_block("b1", ["m1"], 300, t1), _block("b2", ["m2"], 300, t2)]

        with patch(
            "app.services.session_compactor._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 200),
        ) as mock_merge:
            result = await sc.enforce_word_cap(blocks)

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
            "app.services.session_compactor._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 250),
        ) as mock_merge:
            result = await sc.enforce_word_cap(blocks)

            assert mock_merge.await_count == sc.MAX_MERGE_PASSES_PER_CLOSE
            # 8 blocks - 3 merges (each merge removes 1 net block) = 5
            assert len(result) == 8 - sc.MAX_MERGE_PASSES_PER_CLOSE

    @pytest.mark.asyncio
    async def test_odd_block_left_unpaired(self):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block(f"b{i}", [f"m{i}"], 300, base) for i in range(3)]

        with patch(
            "app.services.session_compactor._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 200),
        ):
            result = await sc.enforce_word_cap(blocks)

            # 3 blocks (900 words) -> merge two oldest into 200 words -> 2
            # blocks totalling 500, at cap, loop stops; the odd one (b2) is
            # left untouched rather than special-cased.
            assert len(result) == 2
            block_ids = {b["blockId"] for b in result}
            assert "b2" in block_ids

    @pytest.mark.asyncio
    async def test_merge_failure_keeps_prior_blocks(self):
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        blocks = [_block("b1", ["m1"], 300, t1), _block("b2", ["m2"], 300, t2)]

        with patch(
            "app.services.session_compactor._call_merge_two_blocks_llm",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await sc.enforce_word_cap(blocks)

            assert result == blocks

    def test_word_count(self):
        assert sc._word_count("one two three") == 3
        assert sc._word_count("") == 0


class TestNoDoubleSummarization:
    """Property: the union of sourceSessionIds across all blocks never
    contains a duplicate message ID, before or after any sequence of merges."""

    @pytest.mark.asyncio
    async def test_source_ids_stay_unique_across_repeated_merges(self):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        blocks = [_block(f"b{i}", [f"m{i}"], 300, base) for i in range(6)]

        def _merge_id_count(before: list[dict]) -> int:
            return sum(len(b["sourceSessionIds"]) for b in before)

        total_ids_before = _merge_id_count(blocks)

        with patch(
            "app.services.session_compactor._call_merge_two_blocks_llm",
            new=AsyncMock(return_value="merged " * 200),
        ):
            result = await sc.enforce_word_cap(blocks)

        all_ids = [mid for b in result for mid in b["sourceSessionIds"]]
        assert len(all_ids) == len(set(all_ids))
        assert len(all_ids) == total_ids_before


class TestSyncBlockEmbeddings:
    """_sync_block_embeddings diffs old vs. new blocks by blockId: embeds
    only genuinely new/merged blocks, deletes vectors for blocks that got
    merged away, and never re-embeds an unchanged block."""

    @pytest.mark.asyncio
    async def test_embeds_only_new_blocks(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        unchanged = _block("b1", ["m1"], 50, ts)
        fresh = _block("b2", ["m2"], 50, ts)

        with (
            patch.object(sc, "embed_and_upsert", new=AsyncMock()) as mock_embed,
            patch.object(sc, "delete_vectors", new=AsyncMock()) as mock_delete,
        ):
            await sc._sync_block_embeddings("t1", "u1", [unchanged], [unchanged, fresh])

        mock_embed.assert_called_once()
        assert mock_embed.call_args.kwargs["vector_id"] == "b2"
        assert mock_embed.call_args.kwargs["source"] == "summary_block"
        mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_merged_away_blocks(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        a = _block("b1", ["m1"], 300, ts)
        b = _block("b2", ["m2"], 300, ts)
        merged = _block("b3", ["m1", "m2"], 400, ts)

        with (
            patch.object(sc, "embed_and_upsert", new=AsyncMock()) as mock_embed,
            patch.object(sc, "delete_vectors", new=AsyncMock()) as mock_delete,
        ):
            await sc._sync_block_embeddings("t1", "u1", [a, b], [merged])

        mock_delete.assert_called_once()
        assert set(mock_delete.call_args.args[0]) == {"b1", "b2"}
        mock_embed.assert_called_once()
        assert mock_embed.call_args.kwargs["vector_id"] == "b3"

    @pytest.mark.asyncio
    async def test_noop_when_nothing_changed(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        block = _block("b1", ["m1"], 50, ts)

        with (
            patch.object(sc, "embed_and_upsert", new=AsyncMock()) as mock_embed,
            patch.object(sc, "delete_vectors", new=AsyncMock()) as mock_delete,
        ):
            await sc._sync_block_embeddings("t1", "u1", [block], [block])

        mock_embed.assert_not_called()
        mock_delete.assert_not_called()
