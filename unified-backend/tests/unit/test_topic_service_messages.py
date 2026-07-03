"""Unit tests for TopicService message operations (append_message, get_messages).

Tests cover:
- append_message content validation (≤ 50,000 chars)
- append_message rejects non-active topics
- append_message enforces chronological ordering
- append_message updates lastActiveAt and currentTokenEstimate
- append_message uses optimistic concurrency with retries
- get_messages pagination with limit and before filter
- get_messages ownership check (404 for non-owner)
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.topic_service import TopicService, MAX_MESSAGE_LENGTH, MAX_RETRIES


def _mock_count_tokens(text: str) -> int:
    """Simple heuristic: ~4 chars per token, matching typical English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@pytest.fixture(autouse=True)
def mock_tiktoken():
    """Mock tiktoken's count_tokens to avoid network calls."""
    with patch("app.services.token_counter.count_tokens", side_effect=_mock_count_tokens):
        yield


@pytest.fixture
def topic_service():
    """Create a TopicService instance."""
    return TopicService()


@pytest.fixture
def active_topic():
    """A sample active topic document as stored in MongoDB."""
    return {
        "topicId": "topic-123",
        "userId": "user-abc",
        "title": "Test Topic",
        "status": "active",
        "mode": None,
        "createdAt": datetime(2024, 1, 1, 10, 0, 0),
        "lastActiveAt": datetime(2024, 1, 1, 10, 0, 0),
        "messages": [],
        "compactionCount": 0,
        "metadata": {
            "totalMessageCount": 0,
            "currentTokenEstimate": 0,
        },
        "version": 0,
    }


@pytest.fixture
def sample_message():
    """A valid sample message dict."""
    return {
        "type": "message",
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": "Hello, world!",
        "timestamp": datetime(2024, 1, 1, 10, 1, 0),
    }


def _mock_update_result(modified_count: int):
    """Create a mock MongoDB update result."""
    result = MagicMock()
    result.modified_count = modified_count
    return result


class TestAppendMessage:
    """Tests for TopicService.append_message."""

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_success(self, mock_col, topic_service, active_topic, sample_message):
        """Successful append adds message and updates metadata."""
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = active_topic
        mock_collection.update_one.return_value = _mock_update_result(1)

        result = await topic_service.append_message("topic-123", "user-abc", sample_message)

        assert result is not None
        assert result["content"] == "Hello, world!"
        assert "tokenCount" in result
        assert isinstance(result["tokenCount"], int)
        assert result["tokenCount"] > 0

    @pytest.mark.asyncio
    async def test_append_message_content_too_long(self, topic_service):
        """Reject message content exceeding 50,000 characters."""
        from fastapi import HTTPException

        long_message = {
            "type": "message",
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": "x" * (MAX_MESSAGE_LENGTH + 1),
            "timestamp": datetime(2024, 1, 1, 10, 1, 0),
        }

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.append_message("topic-123", "user-abc", long_message)
        assert exc_info.value.status_code == 400
        assert "50000" in str(exc_info.value.detail) or "50,000" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_rejects_inactive_topic(self, mock_col, topic_service, sample_message):
        """Reject append when topic status is not 'active'."""
        from fastapi import HTTPException

        archived_topic = {
            "topicId": "topic-123",
            "userId": "user-abc",
            "status": "archived",
            "messages": [],
            "metadata": {"totalMessageCount": 0, "currentTokenEstimate": 0},
            "version": 0,
        }
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = archived_topic

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.append_message("topic-123", "user-abc", sample_message)
        assert exc_info.value.status_code == 409
        assert "not active" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_enforces_chronological_order(self, mock_col, topic_service):
        """Reject message with timestamp earlier than last message."""
        from fastapi import HTTPException

        topic_with_messages = {
            "topicId": "topic-123",
            "userId": "user-abc",
            "status": "active",
            "messages": [
                {
                    "type": "message",
                    "id": "msg-1",
                    "role": "user",
                    "content": "First message",
                    "timestamp": datetime(2024, 1, 1, 12, 0, 0),
                    "tokenCount": 5,
                }
            ],
            "metadata": {"totalMessageCount": 1, "currentTokenEstimate": 5},
            "version": 1,
        }

        earlier_message = {
            "type": "message",
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": "This is earlier",
            "timestamp": datetime(2024, 1, 1, 11, 0, 0),  # before the existing message
        }

        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = topic_with_messages

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.append_message("topic-123", "user-abc", earlier_message)
        assert exc_info.value.status_code == 400
        assert "chronological" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_topic_not_found(self, mock_col, topic_service, sample_message):
        """Return 404 when topic doesn't exist or user doesn't own it."""
        from fastapi import HTTPException

        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.append_message("nonexistent", "user-abc", sample_message)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_optimistic_concurrency_retry(self, mock_col, topic_service, active_topic, sample_message):
        """Retry on version conflict and succeed on second attempt."""
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = active_topic
        # First attempt fails (conflict), second succeeds
        mock_collection.update_one.side_effect = [
            _mock_update_result(0),
            _mock_update_result(1),
        ]

        result = await topic_service.append_message("topic-123", "user-abc", sample_message)
        assert result is not None
        assert mock_collection.update_one.call_count == 2

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_conflict_after_max_retries(self, mock_col, topic_service, active_topic, sample_message):
        """Return 409 when all retries are exhausted."""
        from fastapi import HTTPException

        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = active_topic
        mock_collection.update_one.return_value = _mock_update_result(0)

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.append_message("topic-123", "user-abc", sample_message)
        assert exc_info.value.status_code == 409
        assert "conflict" in exc_info.value.detail.lower()
        assert mock_collection.update_one.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_append_message_updates_token_estimate(self, mock_col, topic_service, active_topic, sample_message):
        """Token estimate is updated atomically with the message append."""
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = active_topic
        mock_collection.update_one.return_value = _mock_update_result(1)

        result = await topic_service.append_message("topic-123", "user-abc", sample_message)

        # Verify the update_one call includes the token estimate update
        call_args = mock_collection.update_one.call_args
        update_dict = call_args[0][1]  # second positional arg is the update
        set_fields = update_dict.get("$set", {})
        assert "metadata.currentTokenEstimate" in set_fields
        assert set_fields["metadata.currentTokenEstimate"] == result["tokenCount"]


class TestGetMessages:
    """Tests for TopicService.get_messages."""

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_get_messages_returns_all(self, mock_col, topic_service):
        """Return all messages when count is within limit."""
        messages = [
            {"type": "message", "id": f"msg-{i}", "role": "user", "content": f"Msg {i}", "timestamp": datetime(2024, 1, 1, 10, i, 0), "tokenCount": 3}
            for i in range(5)
        ]
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = {"messages": messages}

        result = await topic_service.get_messages("topic-123", "user-abc")
        assert len(result) == 5
        assert result[0]["id"] == "msg-0"
        assert result[4]["id"] == "msg-4"

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_get_messages_with_limit(self, mock_col, topic_service):
        """Respect limit parameter, returning last N messages in order."""
        messages = [
            {"type": "message", "id": f"msg-{i}", "role": "user", "content": f"Msg {i}", "timestamp": datetime(2024, 1, 1, 10, i, 0), "tokenCount": 3}
            for i in range(10)
        ]
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = {"messages": messages}

        result = await topic_service.get_messages("topic-123", "user-abc", limit=3)
        assert len(result) == 3
        # Should return the last 3 messages (most recent)
        assert result[0]["id"] == "msg-7"
        assert result[2]["id"] == "msg-9"

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_get_messages_with_before_filter(self, mock_col, topic_service):
        """Filter messages to only those before the given timestamp."""
        messages = [
            {"type": "message", "id": f"msg-{i}", "role": "user", "content": f"Msg {i}", "timestamp": datetime(2024, 1, 1, 10, i, 0), "tokenCount": 3}
            for i in range(10)
        ]
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = {"messages": messages}

        # Only get messages before minute 5
        before_ts = datetime(2024, 1, 1, 10, 5, 0).isoformat()
        result = await topic_service.get_messages("topic-123", "user-abc", before=before_ts)
        assert len(result) == 5
        assert all(m["timestamp"] < datetime(2024, 1, 1, 10, 5, 0) for m in result)

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_get_messages_topic_not_found(self, mock_col, topic_service):
        """Return 404 when topic doesn't exist or user doesn't own it."""
        from fastapi import HTTPException

        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.get_messages("nonexistent", "user-abc")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_get_messages_empty_topic(self, mock_col, topic_service):
        """Return empty list for topic with no messages."""
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = {"messages": []}

        result = await topic_service.get_messages("topic-123", "user-abc")
        assert result == []

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_get_messages_before_and_limit(self, mock_col, topic_service):
        """Combine before filter with limit — filter first, then limit."""
        messages = [
            {"type": "message", "id": f"msg-{i}", "role": "user", "content": f"Msg {i}", "timestamp": datetime(2024, 1, 1, 10, i, 0), "tokenCount": 3}
            for i in range(20)
        ]
        mock_collection = AsyncMock()
        mock_col.return_value = mock_collection
        mock_collection.find_one.return_value = {"messages": messages}

        # Filter to messages before minute 15 (15 messages), then limit to 3
        before_ts = datetime(2024, 1, 1, 10, 15, 0).isoformat()
        result = await topic_service.get_messages("topic-123", "user-abc", limit=3, before=before_ts)
        assert len(result) == 3
        # Should be the last 3 of the filtered set (msg-12, msg-13, msg-14)
        assert result[0]["id"] == "msg-12"
        assert result[2]["id"] == "msg-14"
