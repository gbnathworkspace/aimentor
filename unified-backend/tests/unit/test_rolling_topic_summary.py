"""Unit tests for the rolling-topic-summary behavior (issue #23, .kiro/specs/rolling-topic-summary).

Covers:
- _find_rolling_summary: None / single dict / list-of-many
- _call_merge_summarization_llm: delegates cleanly with no prior summary,
  prepends a PRIOR SUMMARY turn when one exists
- _execute_compaction: replaces the existing rolling summary in place
  (union'd compactedMessageIds, advancing compactedRange.to, reused id)
  instead of appending a second block
- _migrate_legacy_summaries: collapses multiple legacy SummaryBlocks into one
  before normal compaction proceeds, and leaves the topic untouched on failure

Requirements: 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.compaction_service import CompactionService, _find_rolling_summary
from app.services.token_counter import TokenCounter


def _make_message(role: str, content: str, token_count: int, msg_id: str, timestamp=None) -> dict:
    return {
        "type": "message",
        "id": msg_id,
        "role": role,
        "content": content,
        "tokenCount": token_count,
        "timestamp": timestamp or datetime(2024, 1, 1, tzinfo=timezone.utc),
    }


def _make_pair(user_tokens: int, assistant_tokens: int, pair_idx: int) -> list[dict]:
    base_ts = datetime(2024, 1, 1, pair_idx, 0, tzinfo=timezone.utc)
    return [
        _make_message("user", f"user msg {pair_idx}", user_tokens, f"u{pair_idx}", base_ts),
        _make_message(
            "assistant", f"assistant msg {pair_idx}", assistant_tokens, f"a{pair_idx}",
            datetime(2024, 1, 1, pair_idx, 1, tzinfo=timezone.utc),
        ),
    ]


def _make_summary(summary_id: str, text: str, from_ts, to_ts, ids: list[str]) -> dict:
    return {
        "type": "summary",
        "id": summary_id,
        "summary": text,
        "compactedMessageIds": ids,
        "compactedRange": {"from": from_ts, "to": to_ts},
        "messageCount": len(ids),
        "tokenCount": 10,
        "createdAt": from_ts,
        "compactionEventId": "evt-0",
    }


class TestFindRollingSummary:
    def test_returns_none_when_no_summaries(self):
        messages = [*_make_pair(100, 100, 1)]
        assert _find_rolling_summary(messages) is None

    def test_returns_single_dict_when_exactly_one(self):
        sb = _make_summary("sb-1", "text", datetime(2024, 1, 1), datetime(2024, 1, 2), ["u1", "a1"])
        messages = [sb, *_make_pair(100, 100, 2)]
        result = _find_rolling_summary(messages)
        assert result is sb

    def test_returns_list_when_multiple_legacy_blocks(self):
        sb1 = _make_summary("sb-1", "first", datetime(2024, 1, 1), datetime(2024, 1, 2), ["u1"])
        sb2 = _make_summary("sb-2", "second", datetime(2024, 1, 3), datetime(2024, 1, 4), ["u2"])
        messages = [sb1, sb2, *_make_pair(100, 100, 5)]
        result = _find_rolling_summary(messages)
        assert isinstance(result, list)
        assert len(result) == 2


class TestCallMergeSummarizationLlm:
    @pytest.mark.asyncio
    async def test_delegates_directly_when_no_existing_summary(self):
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)
        svc._call_summarization_llm = AsyncMock(return_value={"summary": "s", "skill_updates": None})

        selected = _make_pair(100, 100, 1)
        result = await svc._call_merge_summarization_llm(None, selected, "Some Topic")

        svc._call_summarization_llm.assert_called_once_with(selected, "Some Topic")
        assert result["summary"] == "s"

    @pytest.mark.asyncio
    async def test_prepends_prior_summary_turn_when_existing(self):
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)
        svc._call_summarization_llm = AsyncMock(return_value={"summary": "merged", "skill_updates": None})

        existing = _make_summary("sb-1", "prior text", datetime(2024, 1, 1), datetime(2024, 1, 2), ["u0"])
        selected = _make_pair(100, 100, 1)

        result = await svc._call_merge_summarization_llm(existing, selected, "Some Topic")

        call_args = svc._call_summarization_llm.call_args[0]
        called_with = call_args[0]
        assert called_with[0] == {"role": "PRIOR SUMMARY", "content": "prior text"}
        assert called_with[1:] == selected
        assert call_args[1] == "Some Topic"
        assert result["summary"] == "merged"


class TestExecuteCompactionMerge:
    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_second_compaction_replaces_not_appends(self, mock_ct):
        """A topic with one existing rolling summary + new compactable content
        ends up with exactly one summary block, id reused, ids unioned, range advanced."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        existing_summary = _make_summary(
            "sb-1", "Earlier discussion.",
            from_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_ts=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
            ids=["u0", "a0"],
        )
        new_pairs = [*_make_pair(200, 200, 2), *_make_pair(200, 200, 3)]
        messages = [existing_summary, *new_pairs]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 5,
            "compactionCount": 1,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 5},
        }

        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "Merged narrative covering everything so far.",
            "skill_updates": None,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:

            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 1
            mock_col.update_one = AsyncMock(return_value=mock_update_result)
            mock_topics.return_value = mock_col

            mock_events_col = MagicMock()
            mock_events_col.insert_one = AsyncMock()
            mock_events.return_value = mock_events_col

            result = await svc.compact("topic-1", "user-1")

        assert result is not None
        block = result["summaryBlock"]
        assert block["id"] == "sb-1"  # reused, not a new id
        assert block["compactedRange"]["from"] == existing_summary["compactedRange"]["from"]
        assert block["compactedRange"]["to"] > existing_summary["compactedRange"]["to"]
        assert set(block["compactedMessageIds"]) >= {"u0", "a0"}
        assert len(set(block["compactedMessageIds"])) == len(block["compactedMessageIds"])  # no dupes

        # Persisted messages array contains exactly one summary entry
        update_call = mock_col.update_one.call_args
        new_messages = update_call[0][1]["$set"]["messages"]
        summary_entries = [m for m in new_messages if m.get("type") == "summary"]
        assert len(summary_entries) == 1


class TestMigrateLegacySummaries:
    @pytest.mark.asyncio
    async def test_merges_multiple_legacy_blocks_into_one(self):
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        sb1 = _make_summary("sb-1", "first chunk", datetime(2024, 1, 1), datetime(2024, 1, 2), ["u1", "a1"])
        sb2 = _make_summary("sb-2", "second chunk", datetime(2024, 1, 3), datetime(2024, 1, 4), ["u2", "a2"])
        topic = {
            "topicId": "topic-1",
            "userId": "user-1",
            "version": 2,
            "messages": [sb1, sb2, *_make_pair(50, 50, 5)],
        }

        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "Combined summary of both chunks.",
            "skill_updates": None,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 1
            mock_col.update_one = AsyncMock(return_value=mock_update_result)
            mock_topics.return_value = mock_col

            merged = await svc._migrate_legacy_summaries("topic-1", "user-1", topic)

        assert merged is not None
        assert merged["id"] == "sb-1"  # earliest block's id is kept
        assert set(merged["compactedMessageIds"]) == {"u1", "a1", "u2", "a2"}
        assert merged["compactedRange"]["from"] == sb1["compactedRange"]["from"]
        assert merged["compactedRange"]["to"] == sb2["compactedRange"]["to"]
        mock_col.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_leaves_topic_untouched_on_llm_failure(self):
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        sb1 = _make_summary("sb-1", "first", datetime(2024, 1, 1), datetime(2024, 1, 2), ["u1"])
        sb2 = _make_summary("sb-2", "second", datetime(2024, 1, 3), datetime(2024, 1, 4), ["u2"])
        topic = {"topicId": "topic-1", "userId": "user-1", "version": 2, "messages": [sb1, sb2]}

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM down"))

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.update_one = AsyncMock()
            mock_topics.return_value = mock_col

            merged = await svc._migrate_legacy_summaries("topic-1", "user-1", topic)

        assert merged is None
        mock_col.update_one.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_compact_skips_this_turn_when_migration_fails(self, mock_ct):
        """If migration fails, compact() returns None and does not attempt the
        normal merge-on-compact flow this turn (Req 2.2, 2.3)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        sb1 = _make_summary("sb-1", "first", datetime(2024, 1, 1), datetime(2024, 1, 2), ["u1"])
        sb2 = _make_summary("sb-2", "second", datetime(2024, 1, 3), datetime(2024, 1, 4), ["u2"])
        messages = [sb1, sb2, *_make_pair(300, 300, 3)]
        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 2,
            "compactionCount": 2,
            "metadata": {"currentTokenEstimate": 700, "totalMessageCount": 6},
        }

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM down"))

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_col.update_one = AsyncMock()
            mock_topics.return_value = mock_col

            result = await svc.compact("topic-1", "user-1")

        assert result is None
        mock_col.update_one.assert_not_called()
