"""Unit tests for CompactionService error handling and retry logic.

Tests cover:
- LLM failure increments consecutive failure counter
- After 3 failures, get_user_notification returns notification
- Successful compaction resets failure counter
- Skill graph retry (succeeds on 2nd attempt)
- Skill graph fails after 3 retries — logged but summary preserved
- Messages always preserved on LLM failure

Requirements: 10.1, 10.2, 8.4, 8.5
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.compaction_service import (
    MAX_CONSECUTIVE_FAILURES,
    MAX_SKILL_UPDATE_RETRIES,
    CompactionService,
)
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


def _build_topic_doc(messages: list[dict], topic_id: str = "topic-1", user_id: str = "user-1") -> dict:
    """Build a topic document for testing."""
    total_tokens = sum(msg.get("tokenCount", 0) for msg in messages)
    return {
        "topicId": topic_id,
        "userId": user_id,
        "messages": messages,
        "version": 1,
        "compactionCount": 0,
        "metadata": {"currentTokenEstimate": total_tokens, "totalMessageCount": len(messages)},
    }


def _setup_mocks_for_compaction(topic_doc, update_success=True):
    """Set up common mocks for compaction tests. Returns (mock_topics, mock_events) context managers."""
    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(return_value=topic_doc)
    mock_update_result = MagicMock()
    mock_update_result.modified_count = 1 if update_success else 0
    mock_col.update_one = AsyncMock(return_value=mock_update_result)

    mock_events_col = MagicMock()
    mock_events_col.insert_one = AsyncMock()

    return mock_col, mock_events_col


# ---------------------------------------------------------------------------
# Tests: LLM failure tracking (Req 10.1, 10.2)
# ---------------------------------------------------------------------------


class TestLLMFailureTracking:
    """Tests for consecutive LLM failure counter and notification."""

    @pytest.mark.asyncio
    async def test_llm_failure_increments_consecutive_counter(self):
        """When LLM call fails, consecutive failure counter increments (Req 10.1)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        # LLM call fails
        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            result = await svc.compact("topic-1", "user-1")

            assert result is None
            assert svc._consecutive_failures["topic-1"] == 1

    @pytest.mark.asyncio
    async def test_multiple_failures_increment_counter(self):
        """Multiple LLM failures accumulate in the counter."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            for i in range(3):
                await svc.compact("topic-1", "user-1")

            assert svc._consecutive_failures["topic-1"] == 3

    @pytest.mark.asyncio
    async def test_after_3_failures_notification_returned(self):
        """After 3 consecutive failures, get_user_notification returns info (Req 10.2)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            # Before 3 failures — no notification
            assert svc.get_user_notification("topic-1") is None

            for _ in range(3):
                await svc.compact("topic-1", "user-1")

            # After 3 failures — notification present
            notification = svc.get_user_notification("topic-1")
            assert notification is not None
            assert notification["type"] == "compaction_failure"
            assert "new topic" in notification["message"]
            assert notification["consecutive_failures"] == 3

    @pytest.mark.asyncio
    async def test_no_notification_when_below_threshold(self):
        """get_user_notification returns None when failures are below 3."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        # Manually set failures below threshold
        svc._consecutive_failures["topic-1"] = 2
        assert svc.get_user_notification("topic-1") is None

    def test_no_notification_for_unknown_topic(self):
        """get_user_notification returns None for topic with no failure history."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        assert svc.get_user_notification("unknown-topic") is None


# ---------------------------------------------------------------------------
# Tests: Successful compaction resets failure counter
# ---------------------------------------------------------------------------


class TestSuccessResetsFailureCounter:
    """Tests that successful compaction resets the consecutive failure counter."""

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_success_resets_failure_counter(self, mock_ct):
        """Successful compaction resets consecutive failure counter to 0 (Req 10.2)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        # Simulate prior failures
        svc._consecutive_failures["topic-1"] = 2

        # LLM succeeds this time
        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "A summary of the conversation.",
            "skill_updates": None,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            result = await svc.compact("topic-1", "user-1")

            assert result is not None
            assert svc._consecutive_failures["topic-1"] == 0

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_success_after_3_failures_clears_notification(self, mock_ct):
        """After 3 failures and then success, notification is cleared (Req 10.2)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        # Simulate 3 prior failures
        svc._consecutive_failures["topic-1"] = 3
        assert svc.get_user_notification("topic-1") is not None

        # Now success
        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "A summary.",
            "skill_updates": None,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            result = await svc.compact("topic-1", "user-1")

            assert result is not None
            assert svc._consecutive_failures["topic-1"] == 0
            assert svc.get_user_notification("topic-1") is None


# ---------------------------------------------------------------------------
# Tests: Skill graph retry logic (Req 8.4, 8.5)
# ---------------------------------------------------------------------------


class TestSkillGraphRetry:
    """Tests for skill graph update retry logic."""

    @pytest.mark.asyncio
    async def test_skill_update_succeeds_on_second_attempt(self):
        """Skill graph update retries and succeeds on 2nd attempt (Req 8.4)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        skill_updates = [
            {"topic": "BFS", "new_level": "intermediate", "gap": 40, "weak_areas": [], "strong_areas": []}
        ]

        with patch("app.services.skill_graph_repo.apply_update", new_callable=AsyncMock) as mock_apply, \
             patch("app.models.session.SessionSkillUpdate") as mock_ssu:

            mock_ssu.return_value = MagicMock()
            mock_apply.side_effect = [RuntimeError("Temporary DB error"), None]

            await svc._apply_skill_updates("user-1", skill_updates)

            # Should have been called twice (failed first, succeeded second)
            assert mock_apply.call_count == 2

    @pytest.mark.asyncio
    async def test_skill_update_fails_after_max_retries(self):
        """Skill graph permanently fails after 3 retries — logged but no exception (Req 8.5)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        skill_updates = [
            {"topic": "BFS", "new_level": "intermediate", "gap": 40, "weak_areas": [], "strong_areas": []}
        ]

        with patch("app.services.skill_graph_repo.apply_update", new_callable=AsyncMock) as mock_apply, \
             patch("app.models.session.SessionSkillUpdate") as mock_ssu:

            mock_ssu.return_value = MagicMock()
            mock_apply.side_effect = RuntimeError("Persistent DB error")

            # Should NOT raise — failure is handled internally
            await svc._apply_skill_updates("user-1", skill_updates)

            # Should have been called MAX_SKILL_UPDATE_RETRIES times
            assert mock_apply.call_count == MAX_SKILL_UPDATE_RETRIES

    @pytest.mark.asyncio
    @patch("app.services.token_counter.count_tokens", return_value=50)
    async def test_summary_preserved_when_skill_update_fails(self, mock_ct):
        """Summary block is persisted even if skill graph update fails (Req 8.4)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        skill_updates = [
            {"topic": "BFS", "new_level": "intermediate", "gap": 40, "weak_areas": [], "strong_areas": []}
        ]

        svc._call_summarization_llm = AsyncMock(return_value={
            "summary": "Discussion of BFS traversal.",
            "skill_updates": skill_updates,
        })

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events, \
             patch("app.models.session.SessionSkillUpdate") as mock_ssu, \
             patch("app.services.skill_graph_repo.apply_update") as mock_apply:

            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            mock_ssu.return_value = MagicMock()
            mock_apply.side_effect = RuntimeError("Persistent DB error")

            result = await svc.compact("topic-1", "user-1")

            # Compaction succeeds — summary block is in the result
            assert result is not None
            assert result["summaryBlock"] is not None
            assert result["summaryBlock"]["summary"] == "Discussion of BFS traversal."

            # Topic was updated (summary persisted)
            mock_col.update_one.assert_called_once()

            # CompactionEvent was logged
            mock_events_col.insert_one.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Messages always preserved on LLM failure (Req 10.1)
# ---------------------------------------------------------------------------


class TestMessagesPreservedOnFailure:
    """Tests that messages are never modified when compaction fails."""

    @pytest.mark.asyncio
    async def test_messages_unchanged_after_llm_failure(self):
        """On LLM failure, no DB update occurs — messages stay intact (Req 10.1)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            result = await svc.compact("topic-1", "user-1")

            assert result is None
            # The topic's update_one should NOT have been called
            mock_col.update_one.assert_not_called()
            # No compaction event logged
            mock_events_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrency_guard_cleared_after_failure(self):
        """Concurrency guard is cleared after LLM failure (topic can retry later)."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic_doc = _build_topic_doc(messages)

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col, mock_events_col = _setup_mocks_for_compaction(topic_doc)
            mock_topics.return_value = mock_col
            mock_events.return_value = mock_events_col

            await svc.compact("topic-1", "user-1")

        # Guard should be cleared — allows retry on next threshold crossing
        assert "topic-1" not in svc._compaction_in_progress

    @pytest.mark.asyncio
    async def test_failure_counter_independent_per_topic(self):
        """Failure counters are tracked independently per topic."""
        tc = TokenCounter(total_budget=1000, fixed_overhead=0)
        svc = CompactionService(token_counter=tc)

        messages = [*_make_pair(200, 200, 1), *_make_pair(200, 200, 2)]
        topic1_doc = _build_topic_doc(messages, topic_id="topic-1")
        topic2_doc = _build_topic_doc(messages, topic_id="topic-2")

        svc._call_summarization_llm = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.services.compaction_service.topics_col") as mock_topics, \
             patch("app.services.compaction_service.compaction_events_col") as mock_events:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(side_effect=[topic1_doc, topic1_doc, topic2_doc])
            mock_topics.return_value = mock_col

            mock_events_col = MagicMock()
            mock_events_col.insert_one = AsyncMock()
            mock_events.return_value = mock_events_col

            await svc.compact("topic-1", "user-1")
            await svc.compact("topic-1", "user-1")
            await svc.compact("topic-2", "user-1")

            assert svc._consecutive_failures["topic-1"] == 2
            assert svc._consecutive_failures["topic-2"] == 1
