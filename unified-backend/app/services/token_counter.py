"""Token counter utility for topic-based conversation compaction.

Estimates token counts for messages and the overall conversation window.
Used by CompactionService to determine when compaction is needed.

Reuses the tiktoken infrastructure from token_budget.py (cl100k_base encoding).

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

import os
from dataclasses import dataclass
from typing import Any

from app.services.token_budget import count_tokens

# ---------------------------------------------------------------------------
# Configuration (env-configurable with sensible defaults)
# ---------------------------------------------------------------------------

DEFAULT_TOPIC_TOKEN_BUDGET = 200_000
"""Default total context window budget for a topic conversation."""

DEFAULT_FIXED_OVERHEAD = 4_000
"""
Fixed overhead estimate in tokens:
  system prompt ~1500 + L1 Core Profile ~500 + L2 Skill Graph ~1000
  + L3 Episodic RAG ~500 + goal anchor ~500 = ~4000
"""

STALENESS_THRESHOLD = 10
"""Number of messages since last recount before a full recount is triggered."""

COMPACTION_SIGNAL_THRESHOLD = 80
"""Usage percentage at which a compaction-needed signal is emitted (Req 5.5)."""

OVER_CAPACITY_THRESHOLD = 100
"""Usage percentage at which new messages are rejected (Req 5.6)."""


# ---------------------------------------------------------------------------
# Custom exception & signal dataclass
# ---------------------------------------------------------------------------


class OverCapacityError(Exception):
    """Raised when the conversation window exceeds available capacity (Req 5.6)."""

    def __init__(self, current_tokens: int, available_capacity: int):
        self.current_tokens = current_tokens
        self.available_capacity = available_capacity
        pct = int((current_tokens / available_capacity) * 100) if available_capacity > 0 else 999
        super().__init__(
            f"Over capacity: {current_tokens} tokens used out of "
            f"{available_capacity} available ({pct}%)"
        )


@dataclass
class CompactionSignal:
    """Signal emitted when usage exceeds 80% (Req 5.5)."""

    usage_percent: int
    message_count: int
    current_tokens: int
    available_capacity: int


# ---------------------------------------------------------------------------
# TokenCounter class
# ---------------------------------------------------------------------------


def _get_topic_token_budget() -> int:
    """Read total topic token budget from env or use default."""
    env_val = os.environ.get("TOPIC_TOKEN_BUDGET")
    if env_val:
        try:
            parsed = int(env_val)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_TOPIC_TOKEN_BUDGET


def _get_fixed_overhead() -> int:
    """Read fixed overhead from env or use default."""
    env_val = os.environ.get("TOPIC_FIXED_OVERHEAD")
    if env_val:
        try:
            parsed = int(env_val)
            if parsed >= 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_FIXED_OVERHEAD


class TokenCounter:
    """Estimates and tracks token usage for topic conversation windows.

    Uses tiktoken (cl100k_base) via the shared count_tokens() utility
    from app.services.token_budget for accurate token estimation.
    """

    def __init__(
        self,
        total_budget: int | None = None,
        fixed_overhead: int | None = None,
    ):
        """Initialize TokenCounter with configurable budget and overhead.

        Args:
            total_budget: Total context window token budget. Defaults to
                          TOPIC_TOKEN_BUDGET env var or 200,000.
            fixed_overhead: Fixed token overhead (system prompt + L1 + L2 + L3 + goal).
                           Defaults to TOPIC_FIXED_OVERHEAD env var or 4,000.
        """
        self._total_budget = total_budget if total_budget is not None else _get_topic_token_budget()
        self._fixed_overhead = fixed_overhead if fixed_overhead is not None else _get_fixed_overhead()
        self._messages_since_last_count: dict[str, int] = {}
        """Track messages since last full recount, keyed by topic_id."""

    def count_message(self, message: Any) -> int:
        """Estimate token count for a single message using tiktoken (Req 5.1).

        Accepts a message dict or object with a 'content' field.
        Returns an integer token count.
        """
        content = ""
        if isinstance(message, dict):
            content = message.get("content", "")
        elif hasattr(message, "content"):
            content = message.content or ""
        return count_tokens(content)

    def count_window(self, messages: list) -> int:
        """Count total tokens across all messages/summary blocks in the window.

        For each item:
        - If it has a pre-computed 'tokenCount' or 'token_count', use that.
        - Otherwise, estimate via tiktoken.

        This allows cached token counts to be reused without re-encoding.
        """
        total = 0
        for msg in messages:
            if isinstance(msg, dict):
                # Prefer pre-computed token count
                token_count = msg.get("tokenCount") or msg.get("token_count")
                if token_count is not None and isinstance(token_count, int) and token_count > 0:
                    total += token_count
                else:
                    # Fall back to estimation from content or summary
                    content = msg.get("content") or msg.get("summary") or ""
                    total += count_tokens(content)
            elif hasattr(msg, "token_count") and msg.token_count:
                total += msg.token_count
            elif hasattr(msg, "tokenCount") and msg.tokenCount:
                total += msg.tokenCount
            elif hasattr(msg, "content"):
                total += count_tokens(msg.content or "")
            elif hasattr(msg, "summary"):
                total += count_tokens(msg.summary or "")
        return total

    def get_capacity(self) -> int:
        """Return available conversation capacity (Req 5.2).

        Available capacity = total_budget - fixed_overhead.
        """
        return max(0, self._total_budget - self._fixed_overhead)

    def get_usage_percent(self, messages: list) -> int:
        """Return integer usage percentage 0–100+ (Req 5.3).

        Usage % = (current_tokens / available_capacity) × 100.
        """
        capacity = self.get_capacity()
        if capacity <= 0:
            return 100
        current = self.count_window(messages)
        return int((current / capacity) * 100)

    def should_recount(self, messages_since_last_count: int) -> bool:
        """Return True if cached estimate is stale (Req 5.4).

        Staleness threshold: > 10 messages since last recount.
        """
        return messages_since_last_count > STALENESS_THRESHOLD

    def track_message_appended(self, topic_id: str) -> None:
        """Increment the message-since-last-count tracker for a topic."""
        self._messages_since_last_count[topic_id] = (
            self._messages_since_last_count.get(topic_id, 0) + 1
        )

    def reset_recount_tracker(self, topic_id: str) -> None:
        """Reset the message counter after a full recount."""
        self._messages_since_last_count[topic_id] = 0

    def get_messages_since_recount(self, topic_id: str) -> int:
        """Get number of messages appended since last full recount."""
        return self._messages_since_last_count.get(topic_id, 0)

    def check_capacity(self, messages: list) -> CompactionSignal | None:
        """Check if usage exceeds thresholds and return appropriate signal (Req 5.5).

        Returns a CompactionSignal if usage >= 80%, or None if under threshold.
        Raises OverCapacityError if usage >= 100% (Req 5.6).
        """
        capacity = self.get_capacity()
        current_tokens = self.count_window(messages)
        usage_percent = int((current_tokens / capacity) * 100) if capacity > 0 else 100

        # Req 5.6: reject if over 100%
        if usage_percent >= OVER_CAPACITY_THRESHOLD:
            raise OverCapacityError(
                current_tokens=current_tokens,
                available_capacity=capacity,
            )

        # Req 5.5: emit compaction-needed signal at 80%
        if usage_percent >= COMPACTION_SIGNAL_THRESHOLD:
            return CompactionSignal(
                usage_percent=usage_percent,
                message_count=len(messages),
                current_tokens=current_tokens,
                available_capacity=capacity,
            )

        return None
