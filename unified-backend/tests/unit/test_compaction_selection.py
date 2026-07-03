"""Unit tests for CompactionService.select_messages_to_compact.

Tests the message selection logic covering:
- Req 7.1: Select oldest non-summarized messages first
- Req 7.2: Never split user-assistant message pairs
- Req 7.7: Skip compaction if fewer than 2 complete pairs available
"""

from unittest.mock import patch

import pytest

from app.services.compaction_service import CompactionService


def _make_message(role: str, content: str, token_count: int, msg_id: str = "m1") -> dict:
    """Helper to create a message dict with pre-computed token count."""
    return {
        "type": "message",
        "id": msg_id,
        "role": role,
        "content": content,
        "tokenCount": token_count,
    }


def _make_pair(user_tokens: int, assistant_tokens: int, pair_idx: int) -> list[dict]:
    """Helper to create a user-assistant pair with given token counts."""
    return [
        _make_message("user", f"user msg {pair_idx}", user_tokens, f"u{pair_idx}"),
        _make_message("assistant", f"assistant msg {pair_idx}", assistant_tokens, f"a{pair_idx}"),
    ]


def _make_summary_block(summary_id: str = "s1", token_count: int = 50) -> dict:
    """Helper to create a SummaryBlock."""
    return {
        "type": "summary",
        "id": summary_id,
        "summary": "Previously discussed topics...",
        "tokenCount": token_count,
        "compactedMessageIds": ["old1", "old2"],
    }


class TestBasicSelection:
    """Basic selection of oldest pairs first."""

    def test_selects_oldest_pairs_first(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),  # pair 1: 200 tokens
            *_make_pair(100, 100, 2),  # pair 2: 200 tokens
            *_make_pair(100, 100, 3),  # pair 3: 200 tokens
        ]
        # Target 300 tokens → should select pair 1 + pair 2
        result = svc.select_messages_to_compact(messages, target_reclamation=300)
        assert len(result) == 4
        assert result[0]["id"] == "u1"
        assert result[1]["id"] == "a1"
        assert result[2]["id"] == "u2"
        assert result[3]["id"] == "a2"

    def test_selects_single_pair_when_it_meets_target(self):
        svc = CompactionService()
        messages = [
            *_make_pair(200, 200, 1),  # pair 1: 400 tokens
            *_make_pair(100, 100, 2),  # pair 2: 200 tokens
            *_make_pair(100, 100, 3),  # pair 3: 200 tokens
        ]
        # Target 300 tokens → pair 1 alone has 400 tokens, exceeds target
        result = svc.select_messages_to_compact(messages, target_reclamation=300)
        assert len(result) == 2
        assert result[0]["id"] == "u1"
        assert result[1]["id"] == "a1"


class TestPairIntegrity:
    """Never splits user-assistant pairs."""

    def test_includes_full_pair_even_if_exceeds_target(self):
        svc = CompactionService()
        messages = [
            *_make_pair(500, 500, 1),  # pair 1: 1000 tokens
            *_make_pair(100, 100, 2),  # pair 2: 200 tokens
        ]
        # Target 50 tokens — pair 1 exceeds it, but we still include the full pair
        result = svc.select_messages_to_compact(messages, target_reclamation=50)
        assert len(result) == 2
        assert result[0]["id"] == "u1"
        assert result[1]["id"] == "a1"

    def test_never_returns_lone_user_message(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
            _make_message("user", "orphan", 100, "orphan"),  # orphaned user at end
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=500)
        # Should only have complete pairs, never the orphan
        roles = [m["role"] for m in result]
        for i in range(0, len(roles), 2):
            assert roles[i] == "user"
            assert roles[i + 1] == "assistant"

    def test_never_returns_lone_assistant_message(self):
        svc = CompactionService()
        messages = [
            _make_message("assistant", "orphan start", 100, "orphan"),  # orphaned assistant
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=500)
        # Orphan assistant is skipped
        assert all(m["id"] != "orphan" for m in result)
        # All results are complete pairs
        assert len(result) % 2 == 0
        for i in range(0, len(result), 2):
            assert result[i]["role"] == "user"
            assert result[i + 1]["role"] == "assistant"


class TestTargetReclamation:
    """Stops at target reclamation, includes full pair even if it exceeds target."""

    def test_stops_when_target_met(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),  # 200 tokens
            *_make_pair(100, 100, 2),  # 200 tokens
            *_make_pair(100, 100, 3),  # 200 tokens
        ]
        # Target 200 → first pair meets it exactly
        result = svc.select_messages_to_compact(messages, target_reclamation=200)
        assert len(result) == 2
        assert result[0]["id"] == "u1"
        assert result[1]["id"] == "a1"

    def test_includes_pair_that_crosses_target(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),  # 200 tokens
            *_make_pair(100, 100, 2),  # 200 tokens cumulative: 400
            *_make_pair(100, 100, 3),  # 200 tokens cumulative: 600
        ]
        # Target 250 → pair 1 (200) doesn't meet it, so we add pair 2 (400 total)
        result = svc.select_messages_to_compact(messages, target_reclamation=250)
        assert len(result) == 4
        assert result[0]["id"] == "u1"
        assert result[3]["id"] == "a2"

    def test_selects_all_pairs_if_target_not_met(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),  # 200 tokens
            *_make_pair(100, 100, 2),  # 200 tokens
            *_make_pair(100, 100, 3),  # 200 tokens
        ]
        # Target 1000 → all pairs only give 600, select all
        result = svc.select_messages_to_compact(messages, target_reclamation=1000)
        assert len(result) == 6


class TestSummaryBlockSkipping:
    """Skips SummaryBlocks in the selection."""

    def test_skips_summary_blocks(self):
        svc = CompactionService()
        messages = [
            _make_summary_block("s1", 500),  # summary block at start
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
            *_make_pair(100, 100, 3),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=300)
        # Summary block should never appear in selected messages
        assert all(m.get("type") != "summary" for m in result)

    def test_summary_blocks_interspersed(self):
        svc = CompactionService()
        messages = [
            _make_summary_block("s1", 500),
            *_make_pair(100, 100, 1),
            _make_summary_block("s2", 300),
            *_make_pair(100, 100, 2),
            *_make_pair(100, 100, 3),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=300)
        assert all(m.get("type") != "summary" for m in result)
        # Should still select oldest pairs first
        assert result[0]["id"] == "u1"

    def test_all_summaries_returns_empty(self):
        svc = CompactionService()
        messages = [
            _make_summary_block("s1", 500),
            _make_summary_block("s2", 300),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=100)
        assert result == []


class TestMinimumPairsRequirement:
    """Returns empty list when fewer than 2 pairs available."""

    def test_empty_messages_returns_empty(self):
        svc = CompactionService()
        result = svc.select_messages_to_compact([], target_reclamation=100)
        assert result == []

    def test_single_pair_returns_empty(self):
        svc = CompactionService()
        messages = [*_make_pair(100, 100, 1)]
        result = svc.select_messages_to_compact(messages, target_reclamation=50)
        assert result == []

    def test_two_pairs_proceeds_with_selection(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=50)
        assert len(result) > 0

    def test_one_pair_plus_orphan_returns_empty(self):
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),
            _make_message("user", "orphan", 100, "orphan"),
        ]
        # Only 1 complete pair, orphan doesn't count
        result = svc.select_messages_to_compact(messages, target_reclamation=50)
        assert result == []


class TestEdgeCases:
    """Edge cases: empty messages, all summaries, orphaned messages."""

    def test_conversation_starting_with_assistant_message(self):
        """Edge case: conversation starts with an assistant message (rare)."""
        svc = CompactionService()
        messages = [
            _make_message("assistant", "Hello! How can I help?", 50, "orphan_a"),
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=100)
        # The orphan assistant is skipped
        assert all(m["id"] != "orphan_a" for m in result)
        assert len(result) >= 2

    def test_multiple_orphan_users_between_pairs(self):
        """Users without matching assistants between valid pairs."""
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),
            _make_message("user", "orphan 1", 50, "orphan1"),
            _make_message("user", "orphan 2", 50, "orphan2"),
            *_make_pair(100, 100, 2),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=100)
        # Orphans are skipped, valid pairs are selected
        ids = [m["id"] for m in result]
        assert "orphan1" not in ids
        assert "orphan2" not in ids

    def test_zero_target_reclamation_still_selects_first_pair(self):
        """Even with target 0, the first pair is selected (its tokens >= 0)."""
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=0)
        # First pair's tokens (200) >= 0, so we stop after first pair
        assert len(result) == 2
        assert result[0]["id"] == "u1"

    @patch("app.services.token_counter.count_tokens", side_effect=lambda t: max(1, len(t) // 4))
    def test_messages_without_token_count_field(self, mock_ct):
        """Messages missing tokenCount fall back to token counter estimation."""
        svc = CompactionService()
        messages = [
            {"type": "message", "id": "u1", "role": "user", "content": "Hello world"},
            {"type": "message", "id": "a1", "role": "assistant", "content": "Hi there, how can I help?"},
            {"type": "message", "id": "u2", "role": "user", "content": "Teach me about graphs"},
            {"type": "message", "id": "a2", "role": "assistant", "content": "Sure! Let me explain..."},
        ]
        # Should not crash, uses token counter's count_message as fallback
        result = svc.select_messages_to_compact(messages, target_reclamation=1)
        assert len(result) >= 2

    def test_preserves_chronological_order_in_output(self):
        """Selected messages maintain chronological order."""
        svc = CompactionService()
        messages = [
            *_make_pair(100, 100, 1),
            *_make_pair(100, 100, 2),
            *_make_pair(100, 100, 3),
        ]
        result = svc.select_messages_to_compact(messages, target_reclamation=500)
        # Verify order matches original chronological order
        result_ids = [m["id"] for m in result]
        original_ids = [m["id"] for m in messages if m["id"] in result_ids]
        assert result_ids == original_ids
