"""Unit tests for CompactionService.should_compact and compact orchestration.

Tests cover:
- shouldCompact returns True when usage exceeds threshold
- shouldCompact returns False when usage is below threshold
- Pre-emptive check (on_load=True) uses 40% threshold
- Concurrent compaction guard skips second attempt
- compact orchestration flow (mock the LLM call)
- Messages not removed until SummaryBlock persisted (test with mock failure)
- CompactionEvent logged after successful compaction

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.3, 7.4, 7.5, 7.6, 10.3
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.compaction_service import CompactionService
from app.services.token_counter import TokenCounter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(role: str, content: str, token_count: int, msg_id: str, timestamp=None) -> dict:
    """Helper to create a message dict with pre-computed token count."""
    return {
        "type": "message",
        "id": msg_id,
        "role": role,
        "content": content,
        "tokenCount": token_count,
        "timestamp": timestamp or datetime(2024, 1, 1, tzinfo=timezone.utc),
    }


def _make_pair(user_tokens: int, assistant_tokens: int, pair_idx: int) -> list[dict]:
    """Helper to create a user-assistant pair with given token counts."""
    base_ts = datetime(2024, 1, 1, pair_idx, 0, tzinfo=timezone.utc)
    return [
        _make_message("user", f"user msg {pair_idx}", user_tokens, f"u{pair_idx}", base_ts),
        _make_message(
            "assistant", f"assistant msg {pair_idx}", assistant_tokens, f"a{pair_idx}",
            datetime(2024, 1, 1, pair_idx, 1, tzinfo=timezone.utc),
        ),
    ]


def _build_topic_messages(num_pairs: int, tokens_per_msg: int) -> list[dict]:
    """Build a list of message pairs for a topic."""
    messages = []
    for i in range(1, num_pairs + 1):
        messages.extend(_make_pair(tokens_per_msg, tokens_per_msg, i))
    return messages


# ---------------------------------------------------------------------------
# Tests: should_compact
# ---------------------------------------------------------------------------


class TestShouldCompact:
    """Tests for CompactionService.should_compact."""

    @pytest.mark.asyncio
    async def test_returns_true_when_usage_exceeds_threshold(self):
        """shouldCompact returns True when usage exceeds the default 60% threshold."""
        # Set up a token counter with small capacity to make math easy
        # capacity = total_budget - fixed_overhead = 1000 - 0 = 1000
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # 650 tokens = 65% usage → exceeds 60% threshold
        messages = _build_topic_messages(num_pairs=3, tokens_per_msg=108)
        # Each pair = 216 tokens, 3 pairs = 648 tokens ≈ 65%
        # But we want to be precise, so let's use explicit token counts
        messages = [
            _make_message("user", "x" * 100, 325, "u1"),
            _make_message("assistant", "y" * 100, 325, "a1"),
        ]
        # 650 tokens total, 650/1000 = 65% > 60%

        topic_doc = {"topicId": "topic-1", "userId": "user-1", "messages": messages}

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            result = await svc.should_compact("topic-1", "user-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_usage_below_threshold(self):
        """shouldCompact returns False when usage is below the 60% threshold."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # 500 tokens = 50% usage → below 60% threshold
        messages = [
            _make_message("user", "x" * 100, 250, "u1"),
            _make_message("assistant", "y" * 100, 250, "a1"),
        ]

        topic_doc = {"topicId": "topic-1", "userId": "user-1", "messages": messages}

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            result = await svc.should_compact("topic-1", "user-1")
            assert result is False

    @pytest.mark.asyncio
    async def test_preemptive_on_load_uses_40_percent_threshold(self):
        """When on_load=True, uses 40% threshold for pre-emptive compaction."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # 450 tokens = 45% usage → above 40% (on_load) but below 60% (normal)
        messages = [
            _make_message("user", "x" * 100, 225, "u1"),
            _make_message("assistant", "y" * 100, 225, "a1"),
        ]

        topic_doc = {"topicId": "topic-1", "userId": "user-1", "messages": messages}

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            # Normal check → False (45% < 60%)
            result_normal = await svc.should_compact("topic-1", "user-1", on_load=False)
            assert result_normal is False

            # On-load check → True (45% > 40%)
            result_on_load = await svc.should_compact("topic-1", "user-1", on_load=True)
            assert result_on_load is True

    @pytest.mark.asyncio
    async def test_concurrent_compaction_guard_returns_false(self):
        """shouldCompact returns False if compaction is already in progress for the topic."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # Simulate compaction already in progress
        svc._compaction_in_progress.add("topic-1")

        # Even with high usage, should return False
        result = await svc.should_compact("topic-1", "user-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_topic_not_found(self):
        """shouldCompact returns False if topic doesn't exist."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=None)
            mock_topics.return_value = mock_col

            result = await svc.should_compact("nonexistent", "user-1")
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_messages(self):
        """shouldCompact returns False if topic has no messages."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        topic_doc = {"topicId": "topic-1", "userId": "user-1", "messages": []}

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            result = await svc.should_compact("topic-1", "user-1")
            assert result is False


# ---------------------------------------------------------------------------
# Tests: compact orchestration
# ---------------------------------------------------------------------------


class TestCompactOrchestration:
    """Tests for CompactionService.compact orchestration flow."""

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_compact_orchestration_success(self, mock_ct):
        """Full compaction flow: select → summarize → persist → log event."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # Build a topic with usage > 60%
        messages = [
            *_make_pair(200, 200, 1),  # pair 1: 400 tokens
            *_make_pair(200, 200, 2),  # pair 2: 400 tokens
        ]
        # Total: 800 tokens = 80% of 1000 capacity → needs compaction
        # Target: bring below 60% (600 tokens), so reclaim at least 200

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 5,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 4},
        }

        # Mock the LLM call to return a summary
        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "The user discussed topics 1 and 2.",
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

            # Verify compaction result
            assert result is not None
            assert result["messagesCompacted"] > 0
            assert result["tokensReclaimed"] > 0
            assert result["summaryBlock"] is not None
            assert result["summaryBlock"]["type"] == "summary"
            assert result["summaryBlock"]["summary"] == "The user discussed topics 1 and 2."
            assert "compactedMessageIds" in result["summaryBlock"]

            # Verify topic was updated
            mock_col.update_one.assert_called_once()
            update_call = mock_col.update_one.call_args
            # Check version-based optimistic concurrency
            assert update_call[0][0]["version"] == 5

            # Verify CompactionEvent was logged
            mock_events_col.insert_one.assert_called_once()
            event = mock_events_col.insert_one.call_args[0][0]
            assert event["topicId"] == "topic-1"
            assert event["userId"] == "user-1"
            assert event["messagesCompacted"] > 0
            assert event["tokensReclaimed"] > 0

    @pytest.mark.asyncio
    async def test_concurrent_compaction_guard_skips(self):
        """compact returns None if compaction is already in progress for the topic."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # Simulate compaction already in progress
        svc._compaction_in_progress.add("topic-1")

        result = await svc.compact("topic-1", "user-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_guard_cleared_after_compaction(self):
        """The concurrency guard is removed after compaction completes (even on error)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # Mock topic not found → will return None from _execute_compaction
        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=None)
            mock_topics.return_value = mock_col

            await svc.compact("topic-1", "user-1")

        # Guard should be cleared
        assert "topic-1" not in svc._compaction_in_progress

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_messages_not_removed_until_summary_persisted(self, mock_ct):
        """Messages remain unchanged if the MongoDB update fails (Req 10.3)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [
            *_make_pair(200, 200, 1),
            *_make_pair(200, 200, 2),
        ]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 3,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 4},
        }

        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "Summary text",
            "skill_updates": None,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:

            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            # Simulate concurrent write conflict — update fails
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 0
            mock_col.update_one = AsyncMock(return_value=mock_update_result)
            mock_topics.return_value = mock_col

            mock_events_col = MagicMock()
            mock_events_col.insert_one = AsyncMock()
            mock_events.return_value = mock_events_col

            result = await svc.compact("topic-1", "user-1")

            # Compaction should fail gracefully
            assert result is None
            # CompactionEvent should NOT be logged since persistence failed
            mock_events_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_compaction_event_logged_on_success(self, mock_ct):
        """CompactionEvent is written to compaction_events collection on success."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [
            *_make_pair(200, 200, 1),
            *_make_pair(200, 200, 2),
            *_make_pair(100, 100, 3),
        ]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 1,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 1000, "totalMessageCount": 6},
        }

        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "A brief summary of the discussion.",
            "skill_updates": [{"topic": "graphs", "new_level": "intermediate", "gap": 30, "weak_areas": [], "strong_areas": []}],
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events, \
             patch("app.services.compaction_service.CompactionService._apply_skill_updates", new_callable=AsyncMock):

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
            mock_events_col.insert_one.assert_called_once()
            event = mock_events_col.insert_one.call_args[0][0]
            assert event["topicId"] == "topic-1"
            assert event["tokensBeforeCompaction"] > event["tokensAfterCompaction"]
            assert event["skillUpdateGenerated"] is True

    @pytest.mark.asyncio
    async def test_compact_skips_when_insufficient_messages(self):
        """compact returns None when there are too few messages to compact."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # Only 1 pair — select_messages_to_compact will return empty list
        messages = [
            *_make_pair(400, 400, 1),
        ]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 1,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 2},
        }

        with patch("app.services.compaction_service.topics_col") as mock_topics:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            result = await svc.compact("topic-1", "user-1")
            assert result is None

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_compact_with_skill_updates(self, mock_ct):
        """compact calls _apply_skill_updates when LLM returns skill updates."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [
            *_make_pair(200, 200, 1),
            *_make_pair(200, 200, 2),
        ]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 0,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 4},
        }

        skill_updates = [
            {"topic": "BFS", "new_level": "intermediate", "gap": 40, "weak_areas": ["traversal"], "strong_areas": ["basics"]}
        ]

        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "Discussion of BFS.",
            "skill_updates": skill_updates,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events, \
             patch.object(svc, "_apply_skill_updates", new_callable=AsyncMock) as mock_apply:

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
            assert result["skillUpdate"] == skill_updates
            mock_apply.assert_called_once_with("user-1", skill_updates)

    @pytest.mark.asyncio
    async def test_compact_preserves_messages_on_llm_failure(self):
        """If _call_summarization_llm raises, messages are preserved (Req 10.1)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [
            *_make_pair(200, 200, 1),
            *_make_pair(200, 200, 2),
        ]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 1,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 4},
        }

        # LLM call fails
        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:

            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_col.update_one = AsyncMock()
            mock_topics.return_value = mock_col

            mock_events_col = MagicMock()
            mock_events_col.insert_one = AsyncMock()
            mock_events.return_value = mock_events_col

            # compact now catches the exception and returns None (Req 10.1)
            result = await svc.compact("topic-1", "user-1")
            assert result is None

            # Topic update should NOT have been called — messages preserved
            mock_col.update_one.assert_not_called()
            # CompactionEvent should NOT be logged
            mock_events_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_guard_cleared_after_llm_failure(self):
        """Concurrency guard is cleared even when LLM call fails."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [
            *_make_pair(200, 200, 1),
            *_make_pair(200, 200, 2),
        ]

        topic_doc = {
            "topicId": "topic-1",
            "userId": "user-1",
            "messages": messages,
            "version": 1,
            "compactionCount": 0,
            "metadata": {"currentTokenEstimate": 800, "totalMessageCount": 4},
        }

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col"):

            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            # compact now catches the exception and returns None
            result = await svc.compact("topic-1", "user-1")
            assert result is None

        # Guard should be cleared despite the error
        assert "topic-1" not in svc._compaction_in_progress
