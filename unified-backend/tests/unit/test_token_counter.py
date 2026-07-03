"""Unit tests for app/services/token_counter.py.

Tests the TokenCounter class covering:
- Req 5.1: Token estimation via tiktoken
- Req 5.2: Available capacity calculation
- Req 5.3: Usage percentage calculation
- Req 5.4: Staleness detection
- Req 5.5: Compaction-needed signal at 80%
- Req 5.6: Over-capacity rejection at 100%
"""

import os
from unittest.mock import patch

import pytest

from app.services.token_counter import (
    COMPACTION_SIGNAL_THRESHOLD,
    DEFAULT_FIXED_OVERHEAD,
    DEFAULT_TOPIC_TOKEN_BUDGET,
    OVER_CAPACITY_THRESHOLD,
    STALENESS_THRESHOLD,
    CompactionSignal,
    OverCapacityError,
    TokenCounter,
)


def _mock_count_tokens(text: str) -> int:
    """Simple heuristic: ~4 chars per token, matching typical English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class TestCountMessage:
    """Req 5.1: Token estimation for individual messages."""

    @patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens)
    def test_counts_tokens_for_dict_message(self, mock_ct):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        msg = {"content": "Hello, world!", "role": "user"}
        token_count = tc.count_message(msg)
        assert token_count > 0
        assert isinstance(token_count, int)

    @patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens)
    def test_counts_tokens_for_object_message(self, mock_ct):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)

        class Msg:
            content = "Hello, this is a test message."

        token_count = tc.count_message(Msg())
        assert token_count > 0

    @patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens)
    def test_empty_content_is_zero(self, mock_ct):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.count_message({"content": ""}) == 0
        assert tc.count_message({"content": None}) == 0
        assert tc.count_message({}) == 0

    @patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens)
    def test_longer_messages_have_more_tokens(self, mock_ct):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        short = tc.count_message({"content": "Hi"})
        long = tc.count_message({"content": "This is a much longer message with several words."})
        assert long > short


class TestCountWindow:
    """Token counting for a list of messages/summary blocks."""

    @patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens)
    def test_sums_all_messages(self, mock_ct):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        messages = [
            {"content": "Hello", "role": "user"},
            {"content": "Hi there! How can I help?", "role": "assistant"},
        ]
        total = tc.count_window(messages)
        assert total > 0
        # Should roughly equal sum of individual counts
        expected = tc.count_message(messages[0]) + tc.count_message(messages[1])
        assert total == expected

    def test_uses_precomputed_token_count(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        messages = [
            {"content": "Hello", "role": "user", "tokenCount": 42},
            {"content": "World", "role": "assistant", "tokenCount": 55},
        ]
        # Should use the precomputed values, not re-encode
        assert tc.count_window(messages) == 97

    def test_uses_snake_case_token_count(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        messages = [{"content": "Hello", "token_count": 30}]
        assert tc.count_window(messages) == 30

    def test_summary_block_counted_by_summary_field(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        summary_block = {
            "type": "summary",
            "summary": "Previously discussed BFS and DFS algorithms.",
            "tokenCount": 10,
        }
        # Should use pre-computed tokenCount
        assert tc.count_window([summary_block]) == 10

    @patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens)
    def test_summary_block_fallback_to_content(self, mock_ct):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        # No precomputed tokenCount, so falls back to encoding the summary
        summary_block = {
            "type": "summary",
            "summary": "Previously discussed BFS and DFS algorithms.",
        }
        count = tc.count_window([summary_block])
        assert count > 0

    def test_empty_window_is_zero(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.count_window([]) == 0


class TestGetCapacity:
    """Req 5.2: Available capacity = total_budget - fixed_overhead."""

    def test_default_capacity(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.get_capacity() == 196_000

    def test_custom_capacity(self):
        tc = TokenCounter(total_budget=100_000, fixed_overhead=10_000)
        assert tc.get_capacity() == 90_000

    def test_overhead_exceeds_budget_returns_zero(self):
        tc = TokenCounter(total_budget=1_000, fixed_overhead=5_000)
        assert tc.get_capacity() == 0

    def test_env_configurable_budget(self):
        with patch.dict(os.environ, {"TOPIC_TOKEN_BUDGET": "150000"}, clear=False):
            tc = TokenCounter()
            assert tc._total_budget == 150_000

    def test_env_configurable_overhead(self):
        with patch.dict(os.environ, {"TOPIC_FIXED_OVERHEAD": "6000"}, clear=False):
            tc = TokenCounter()
            assert tc._fixed_overhead == 6_000

    def test_invalid_env_falls_back_to_default(self):
        with patch.dict(
            os.environ,
            {"TOPIC_TOKEN_BUDGET": "notanumber", "TOPIC_FIXED_OVERHEAD": "-1"},
            clear=False,
        ):
            tc = TokenCounter()
            assert tc._total_budget == DEFAULT_TOPIC_TOKEN_BUDGET
            # -1 is invalid (< 0), falls back to default
            assert tc._fixed_overhead == DEFAULT_FIXED_OVERHEAD


class TestGetUsagePercent:
    """Req 5.3: Usage % = (current_tokens / available_capacity) × 100."""

    def test_empty_window_is_zero_percent(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.get_usage_percent([]) == 0

    def test_half_capacity_is_50_percent(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()  # 196,000
        # Create messages with precomputed token counts totaling ~50% of capacity
        half_tokens = capacity // 2
        messages = [{"content": "x", "tokenCount": half_tokens}]
        assert tc.get_usage_percent(messages) == 50

    def test_full_capacity_is_100_percent(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()
        messages = [{"content": "x", "tokenCount": capacity}]
        assert tc.get_usage_percent(messages) == 100

    def test_zero_capacity_returns_100(self):
        tc = TokenCounter(total_budget=100, fixed_overhead=200)
        assert tc.get_usage_percent([{"content": "hi", "tokenCount": 5}]) == 100


class TestShouldRecount:
    """Req 5.4: Staleness detection — recount if >10 messages since last recalculation."""

    def test_under_threshold_returns_false(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.should_recount(5) is False
        assert tc.should_recount(10) is False

    def test_over_threshold_returns_true(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.should_recount(11) is True
        assert tc.should_recount(50) is True

    def test_exact_threshold_returns_false(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        assert tc.should_recount(STALENESS_THRESHOLD) is False

    def test_tracking_messages(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        topic_id = "topic-abc"
        # Initially zero
        assert tc.get_messages_since_recount(topic_id) == 0
        # Track appends
        for _ in range(11):
            tc.track_message_appended(topic_id)
        assert tc.get_messages_since_recount(topic_id) == 11
        assert tc.should_recount(tc.get_messages_since_recount(topic_id)) is True
        # Reset
        tc.reset_recount_tracker(topic_id)
        assert tc.get_messages_since_recount(topic_id) == 0


class TestCheckCapacity:
    """Req 5.5: Compaction signal at 80%. Req 5.6: Over-capacity rejection at 100%."""

    def test_under_threshold_returns_none(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()
        # 50% usage — well under threshold
        messages = [{"content": "x", "tokenCount": capacity // 2}]
        assert tc.check_capacity(messages) is None

    def test_at_80_percent_returns_signal(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()
        tokens_at_80 = int(capacity * 0.80)
        messages = [{"content": "x", "tokenCount": tokens_at_80}]
        signal = tc.check_capacity(messages)
        assert signal is not None
        assert isinstance(signal, CompactionSignal)
        assert signal.usage_percent == 80
        assert signal.message_count == 1
        assert signal.current_tokens == tokens_at_80
        assert signal.available_capacity == capacity

    def test_at_90_percent_returns_signal(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()
        tokens_at_90 = int(capacity * 0.90)
        messages = [{"content": "x", "tokenCount": tokens_at_90}]
        signal = tc.check_capacity(messages)
        assert signal is not None
        assert signal.usage_percent == 90

    def test_at_100_percent_raises_over_capacity(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()
        messages = [{"content": "x", "tokenCount": capacity}]
        with pytest.raises(OverCapacityError) as exc_info:
            tc.check_capacity(messages)
        assert exc_info.value.current_tokens == capacity
        assert exc_info.value.available_capacity == capacity

    def test_over_100_percent_raises_over_capacity(self):
        tc = TokenCounter(total_budget=200_000, fixed_overhead=4_000)
        capacity = tc.get_capacity()
        messages = [{"content": "x", "tokenCount": capacity + 5000}]
        with pytest.raises(OverCapacityError):
            tc.check_capacity(messages)

    def test_signal_contains_message_count(self):
        tc = TokenCounter(total_budget=10_000, fixed_overhead=1_000)
        capacity = tc.get_capacity()  # 9,000
        # 85% → signal
        tokens_each = int(capacity * 0.85) // 3
        messages = [
            {"content": "a", "tokenCount": tokens_each},
            {"content": "b", "tokenCount": tokens_each},
            {"content": "c", "tokenCount": tokens_each},
        ]
        signal = tc.check_capacity(messages)
        assert signal is not None
        assert signal.message_count == 3


class TestOverCapacityError:
    """Test the custom exception attributes."""

    def test_error_message_contains_details(self):
        err = OverCapacityError(current_tokens=200_000, available_capacity=196_000)
        assert "200000" in str(err)
        assert "196000" in str(err)

    def test_attributes_stored(self):
        err = OverCapacityError(current_tokens=100, available_capacity=50)
        assert err.current_tokens == 100
        assert err.available_capacity == 50
