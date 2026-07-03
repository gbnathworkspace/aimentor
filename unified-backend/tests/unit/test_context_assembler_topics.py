"""Unit tests for context_assembler.py topic conversation window preparation.

Tests the prepare_conversation_window() function which handles mixed
Messages and SummaryBlocks for topic-based conversations.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import logging
from datetime import datetime, timezone

import pytest

from app.services.context_assembler import (
    _validate_thread_entry,
    prepare_conversation_window,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_message(
    role: str = "user",
    content: str = "Hello",
    timestamp: str | datetime = "2024-01-15T10:00:00Z",
    token_count: int = 10,
    msg_id: str = "msg-1",
) -> dict:
    """Create a valid message dict."""
    return {
        "type": "message",
        "id": msg_id,
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "tokenCount": token_count,
    }


def _make_summary_block(
    summary: str = "Summary of earlier conversation",
    from_ts: str | datetime = "2024-01-10T08:00:00Z",
    to_ts: str | datetime = "2024-01-10T12:00:00Z",
    token_count: int = 50,
    block_id: str = "summary-1",
) -> dict:
    """Create a valid SummaryBlock dict."""
    return {
        "type": "summary",
        "id": block_id,
        "summary": summary,
        "compactedMessageIds": ["m1", "m2", "m3"],
        "compactedRange": {
            "from": from_ts,
            "to": to_ts,
        },
        "messageCount": 3,
        "tokenCount": token_count,
        "createdAt": "2024-01-14T20:00:00Z",
        "compactionEventId": "evt-1",
    }


# ---------------------------------------------------------------------------
# Tests: _validate_thread_entry
# ---------------------------------------------------------------------------


class TestValidateThreadEntry:
    """Validate the _validate_thread_entry helper."""

    def test_valid_message(self):
        msg = _make_message()
        assert _validate_thread_entry(msg) is True

    def test_valid_summary_block(self):
        block = _make_summary_block()
        assert _validate_thread_entry(block) is True

    def test_message_missing_role(self):
        msg = _make_message()
        del msg["role"]
        assert _validate_thread_entry(msg) is False

    def test_message_invalid_role(self):
        msg = _make_message(role="system")
        assert _validate_thread_entry(msg) is False

    def test_message_missing_content(self):
        msg = _make_message()
        del msg["content"]
        assert _validate_thread_entry(msg) is False

    def test_message_empty_content(self):
        msg = _make_message(content="")
        assert _validate_thread_entry(msg) is False

    def test_message_missing_timestamp(self):
        msg = _make_message()
        del msg["timestamp"]
        assert _validate_thread_entry(msg) is False

    def test_summary_missing_id(self):
        block = _make_summary_block()
        del block["id"]
        assert _validate_thread_entry(block) is False

    def test_summary_missing_summary_text(self):
        block = _make_summary_block()
        del block["summary"]
        assert _validate_thread_entry(block) is False

    def test_summary_empty_summary_text(self):
        block = _make_summary_block(summary="")
        assert _validate_thread_entry(block) is False

    def test_summary_missing_compacted_range(self):
        block = _make_summary_block()
        del block["compactedRange"]
        assert _validate_thread_entry(block) is False

    def test_summary_missing_compacted_range_from(self):
        block = _make_summary_block()
        del block["compactedRange"]["from"]
        assert _validate_thread_entry(block) is False

    def test_summary_missing_compacted_range_to(self):
        block = _make_summary_block()
        del block["compactedRange"]["to"]
        assert _validate_thread_entry(block) is False

    def test_summary_missing_token_count(self):
        block = _make_summary_block()
        del block["tokenCount"]
        assert _validate_thread_entry(block) is False

    def test_summary_negative_token_count(self):
        block = _make_summary_block(token_count=-5)
        assert _validate_thread_entry(block) is False

    def test_unknown_type(self):
        entry = {"type": "unknown", "id": "x"}
        assert _validate_thread_entry(entry) is False

    def test_missing_type(self):
        entry = {"id": "x", "content": "hi"}
        assert _validate_thread_entry(entry) is False

    def test_non_dict_entry(self):
        assert _validate_thread_entry("not a dict") is False
        assert _validate_thread_entry(None) is False
        assert _validate_thread_entry(42) is False


# ---------------------------------------------------------------------------
# Tests: prepare_conversation_window
# ---------------------------------------------------------------------------


class TestPrepareConversationWindow:
    """Test prepare_conversation_window with various inputs."""

    def test_empty_messages_returns_empty(self):
        """Empty messages list returns empty."""
        assert prepare_conversation_window([]) == []

    def test_messages_without_summary_blocks_pass_through(self):
        """Messages without SummaryBlocks pass through unchanged in order."""
        msg1 = _make_message(msg_id="m1", timestamp="2024-01-15T10:00:00Z")
        msg2 = _make_message(
            role="assistant",
            content="Hi there",
            msg_id="m2",
            timestamp="2024-01-15T10:01:00Z",
        )
        msg3 = _make_message(msg_id="m3", timestamp="2024-01-15T10:05:00Z", content="Question")

        result = prepare_conversation_window([msg1, msg2, msg3])

        assert len(result) == 3
        assert result[0]["id"] == "m1"
        assert result[1]["id"] == "m2"
        assert result[2]["id"] == "m3"

    def test_mixed_messages_and_summary_blocks(self):
        """Mixed messages and SummaryBlocks are included and ordered."""
        # Summary covers Jan 10, messages are Jan 15
        summary = _make_summary_block(
            from_ts="2024-01-10T08:00:00Z",
            to_ts="2024-01-10T12:00:00Z",
        )
        msg1 = _make_message(msg_id="m1", timestamp="2024-01-15T10:00:00Z")
        msg2 = _make_message(
            role="assistant", content="Response", msg_id="m2", timestamp="2024-01-15T10:01:00Z"
        )

        result = prepare_conversation_window([msg1, summary, msg2])

        # Summary should come first (Jan 10 < Jan 15)
        assert len(result) == 3
        assert result[0]["type"] == "summary"
        assert result[1]["id"] == "m1"
        assert result[2]["id"] == "m2"

    def test_skips_malformed_summary_block(self, caplog):
        """Malformed SummaryBlock (missing required fields) is skipped with warning."""
        valid_msg = _make_message(msg_id="m1", timestamp="2024-01-15T10:00:00Z")
        malformed_summary = {
            "type": "summary",
            "id": "bad-1",
            # Missing: summary, compactedRange, tokenCount
        }

        with caplog.at_level(logging.WARNING):
            result = prepare_conversation_window([valid_msg, malformed_summary])

        assert len(result) == 1
        assert result[0]["id"] == "m1"
        assert "malformed thread entry" in caplog.text.lower()

    def test_chronological_ordering_maintained(self):
        """Output maintains chronological order regardless of input order."""
        msg_early = _make_message(msg_id="early", timestamp="2024-01-15T08:00:00Z")
        msg_late = _make_message(msg_id="late", timestamp="2024-01-15T12:00:00Z")
        msg_mid = _make_message(
            role="assistant", content="Mid", msg_id="mid", timestamp="2024-01-15T10:00:00Z"
        )

        # Pass in non-chronological order
        result = prepare_conversation_window([msg_late, msg_early, msg_mid])

        assert [e["id"] for e in result] == ["early", "mid", "late"]

    def test_summary_block_positioned_by_compacted_range_from(self):
        """SummaryBlock positioned by compactedRange.from, not createdAt (Req 9.2)."""
        # Summary was created on Jan 14, but covers messages from Jan 12
        summary = _make_summary_block(
            from_ts="2024-01-12T08:00:00Z",
            to_ts="2024-01-12T18:00:00Z",
            block_id="s1",
        )
        # Message from Jan 11 (before summary range)
        msg_before = _make_message(msg_id="before", timestamp="2024-01-11T10:00:00Z")
        # Message from Jan 13 (after summary range)
        msg_after = _make_message(msg_id="after", timestamp="2024-01-13T10:00:00Z")

        result = prepare_conversation_window([msg_after, summary, msg_before])

        assert result[0]["id"] == "before"  # Jan 11
        assert result[1]["type"] == "summary"  # Jan 12 (compactedRange.from)
        assert result[2]["id"] == "after"  # Jan 13

    def test_token_budget_enforcement_drops_oldest(self):
        """When max_tokens is set, drops oldest entries to fit within budget."""
        # Each message has tokenCount=100
        msg1 = _make_message(msg_id="m1", timestamp="2024-01-15T08:00:00Z", token_count=100)
        msg2 = _make_message(
            role="assistant",
            content="R1",
            msg_id="m2",
            timestamp="2024-01-15T09:00:00Z",
            token_count=100,
        )
        msg3 = _make_message(msg_id="m3", timestamp="2024-01-15T10:00:00Z", token_count=100)
        msg4 = _make_message(
            role="assistant",
            content="R2",
            msg_id="m4",
            timestamp="2024-01-15T11:00:00Z",
            token_count=100,
        )

        # Budget of 250 can hold 2 messages (200 tokens) but not all 4 (400 tokens)
        result = prepare_conversation_window([msg1, msg2, msg3, msg4], max_tokens=250)

        # Should drop oldest entries to fit
        assert len(result) == 2
        # Remaining should be the most recent
        assert result[0]["id"] == "m3"
        assert result[1]["id"] == "m4"

    def test_token_budget_counts_summary_block_token_count(self):
        """SummaryBlock tokenCount is counted toward the window budget (Req 9.4)."""
        summary = _make_summary_block(
            from_ts="2024-01-10T08:00:00Z",
            to_ts="2024-01-10T12:00:00Z",
            token_count=200,
            block_id="s1",
        )
        msg1 = _make_message(msg_id="m1", timestamp="2024-01-15T10:00:00Z", token_count=50)

        # Budget of 100 — summary alone is 200, so it gets dropped
        result = prepare_conversation_window([summary, msg1], max_tokens=100)

        # Only msg1 fits (50 tokens)
        assert len(result) == 1
        assert result[0]["id"] == "m1"

    def test_token_budget_none_means_no_limit(self):
        """When max_tokens is None, all valid entries are returned."""
        messages = [
            _make_message(msg_id=f"m{i}", timestamp=f"2024-01-15T{10+i:02d}:00:00Z", token_count=1000)
            for i in range(10)
        ]
        result = prepare_conversation_window(messages, max_tokens=None)
        assert len(result) == 10

    def test_token_budget_zero_means_no_limit(self):
        """When max_tokens is 0, function treats it as no limit (guard)."""
        messages = [
            _make_message(msg_id="m1", timestamp="2024-01-15T10:00:00Z", token_count=100)
        ]
        # max_tokens=0 should be treated as no-limit (the condition is max_tokens > 0)
        result = prepare_conversation_window(messages, max_tokens=0)
        assert len(result) == 1

    def test_all_entries_malformed_returns_empty(self, caplog):
        """If all entries are malformed, return empty list."""
        entries = [
            {"type": "summary", "id": "bad"},  # missing required fields
            {"type": "message"},  # missing everything
            "not a dict",
        ]
        with caplog.at_level(logging.WARNING):
            result = prepare_conversation_window(entries)

        assert result == []

    def test_datetime_objects_as_timestamps(self):
        """Works with datetime objects (not just ISO strings) for timestamps."""
        dt1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

        msg1 = _make_message(msg_id="m1", timestamp=dt1)
        msg2 = _make_message(role="assistant", content="Hi", msg_id="m2", timestamp=dt2)

        result = prepare_conversation_window([msg2, msg1])
        assert result[0]["id"] == "m1"
        assert result[1]["id"] == "m2"

    def test_multiple_summary_blocks_ordered_correctly(self):
        """Multiple SummaryBlocks are each positioned by their compactedRange.from."""
        summary_early = _make_summary_block(
            from_ts="2024-01-05T08:00:00Z",
            to_ts="2024-01-05T12:00:00Z",
            block_id="s1",
            token_count=30,
        )
        summary_mid = _make_summary_block(
            from_ts="2024-01-08T08:00:00Z",
            to_ts="2024-01-08T18:00:00Z",
            block_id="s2",
            token_count=30,
        )
        msg = _make_message(msg_id="m1", timestamp="2024-01-10T10:00:00Z")

        result = prepare_conversation_window([msg, summary_mid, summary_early])

        assert result[0]["id"] == "s1"  # Jan 5
        assert result[1]["id"] == "s2"  # Jan 8
        assert result[2]["id"] == "m1"  # Jan 10
