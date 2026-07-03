"""Unit tests for the session-to-topic migration script.

Tests cover:
- Session with messages is correctly converted to a topic
- Session with zero messages is skipped
- Already-migrated session is skipped (idempotency)
- Title derivation logic (existing title vs derived from mode/topic)
- Message role normalization ("mentor" → "assistant")
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from scripts.migrate_sessions_to_topics import (
    build_topic_document,
    convert_message,
    derive_title,
    estimate_token_count,
    migrate_sessions,
    normalize_role,
)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _make_session(
    messages=None,
    title="Untitled session",
    mode="topic",
    topic=None,
    session_id=None,
    user_id="user-123",
    created_at="2024-01-15T10:00:00Z",
):
    """Create a sample session document."""
    if session_id is None:
        session_id = str(uuid4())
    return {
        "session_id": session_id,
        "user_id": user_id,
        "title": title,
        "mode": mode,
        "topic": topic,
        "messages": messages or [],
        "created_at": created_at,
        "updated_at": created_at,
        "status": "ended",
    }


def _make_message(role="user", content="Hello", timestamp="2024-01-15T10:01:00Z"):
    """Create a sample session message."""
    return {
        "role": role,
        "content": content,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Title Derivation Tests
# ---------------------------------------------------------------------------


class TestDeriveTitle:
    """Tests for derive_title function."""

    def test_uses_existing_title_when_present(self):
        session = _make_session(title="My Custom Title")
        assert derive_title(session) == "My Custom Title"

    def test_ignores_untitled_session_title(self):
        session = _make_session(title="Untitled session", mode="topic", topic="Graphs")
        result = derive_title(session)
        assert result == "Topic Session - Graphs"

    def test_derives_from_mode_and_topic(self):
        session = _make_session(title="Untitled session", mode="doubt", topic="Recursion")
        result = derive_title(session)
        assert result == "Doubt Session - Recursion"

    def test_derives_from_mode_only_when_no_topic(self):
        session = _make_session(title="Untitled session", mode="planning", topic=None)
        result = derive_title(session)
        assert result == "Planning Session"

    def test_truncates_long_title_to_100_chars(self):
        long_title = "A" * 150
        session = _make_session(title=long_title)
        result = derive_title(session)
        assert len(result) == 100

    def test_strips_whitespace_from_title(self):
        session = _make_session(title="  Padded Title  ")
        result = derive_title(session)
        assert result == "Padded Title"

    def test_empty_title_treated_as_untitled(self):
        session = _make_session(title="", mode="evaluation", topic="Trees")
        result = derive_title(session)
        assert result == "Evaluation Session - Trees"

    def test_whitespace_only_title_treated_as_untitled(self):
        session = _make_session(title="   ", mode="topic", topic="Arrays")
        result = derive_title(session)
        assert result == "Topic Session - Arrays"


# ---------------------------------------------------------------------------
# Role Normalization Tests
# ---------------------------------------------------------------------------


class TestNormalizeRole:
    """Tests for normalize_role function."""

    def test_mentor_normalized_to_assistant(self):
        assert normalize_role("mentor") == "assistant"

    def test_assistant_unchanged(self):
        assert normalize_role("assistant") == "assistant"

    def test_user_unchanged(self):
        assert normalize_role("user") == "user"


# ---------------------------------------------------------------------------
# Message Conversion Tests
# ---------------------------------------------------------------------------


class TestConvertMessage:
    """Tests for convert_message function."""

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    def test_converts_message_with_all_fields(self, mock_count):
        msg = _make_message(role="user", content="Hello world", timestamp="2024-01-15T10:01:00Z")
        result = convert_message(msg)

        assert result["type"] == "message"
        assert result["role"] == "user"
        assert result["content"] == "Hello world"
        assert result["timestamp"] == "2024-01-15T10:01:00Z"
        assert result["tokenCount"] == 5
        assert "id" in result  # UUID generated

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=3)
    def test_normalizes_mentor_role(self, mock_count):
        msg = _make_message(role="mentor", content="Let me explain")
        result = convert_message(msg)
        assert result["role"] == "assistant"

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=0)
    def test_uses_fallback_timestamp_when_none(self, mock_count):
        msg = {"role": "user", "content": "Hi", "timestamp": None}
        result = convert_message(msg, fallback_timestamp="2024-01-01T00:00:00Z")
        assert result["timestamp"] == "2024-01-01T00:00:00Z"

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=0)
    def test_uses_fallback_when_timestamp_missing(self, mock_count):
        msg = {"role": "user", "content": "Hi"}
        result = convert_message(msg, fallback_timestamp="2024-01-01T00:00:00Z")
        assert result["timestamp"] == "2024-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Topic Document Building Tests
# ---------------------------------------------------------------------------


class TestBuildTopicDocument:
    """Tests for build_topic_document function."""

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=10)
    def test_builds_complete_topic_from_session(self, mock_count):
        session = _make_session(
            title="My Session",
            mode="topic",
            topic="Graphs",
            user_id="user-456",
            session_id="sess-abc",
            messages=[
                _make_message(role="user", content="Hello", timestamp="2024-01-15T10:01:00Z"),
                _make_message(role="assistant", content="Hi there", timestamp="2024-01-15T10:01:30Z"),
            ],
        )

        result = build_topic_document(session)

        assert result["userId"] == "user-456"
        assert result["title"] == "My Session"
        assert result["status"] == "active"
        assert result["mode"] == "topic"
        assert result["lastActiveAt"] == "2024-01-15T10:01:30Z"
        assert result["compactionCount"] == 0
        assert result["version"] == 0
        assert result["migratedFrom"] == "sess-abc"
        assert len(result["messages"]) == 2
        assert result["metadata"]["totalMessageCount"] == 2
        assert result["metadata"]["currentTokenEstimate"] == 20  # 10 per message × 2

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    def test_preserves_message_order(self, mock_count):
        messages = [
            _make_message(role="user", content="First", timestamp="2024-01-15T10:00:00Z"),
            _make_message(role="assistant", content="Second", timestamp="2024-01-15T10:00:30Z"),
            _make_message(role="user", content="Third", timestamp="2024-01-15T10:01:00Z"),
        ]
        session = _make_session(messages=messages)
        result = build_topic_document(session)

        assert result["messages"][0]["content"] == "First"
        assert result["messages"][1]["content"] == "Second"
        assert result["messages"][2]["content"] == "Third"

    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    def test_sets_created_at_from_session(self, mock_count):
        session = _make_session(
            messages=[_make_message()],
            created_at="2024-03-01T08:00:00Z",
        )
        result = build_topic_document(session)
        assert result["createdAt"] == "2024-03-01T08:00:00Z"


# ---------------------------------------------------------------------------
# Full Migration Flow Tests (async)
# ---------------------------------------------------------------------------


class TestMigrateSessions:
    """Tests for the migrate_sessions async function."""

    @pytest.mark.asyncio
    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    async def test_migrates_session_with_messages(self, mock_count):
        session = _make_session(
            session_id="sess-1",
            messages=[
                _make_message(role="user", content="Q1"),
                _make_message(role="assistant", content="A1"),
            ],
        )

        mock_sessions_col = MagicMock()
        mock_sessions_col.find.return_value.to_list = AsyncMock(return_value=[session])

        mock_topics_col = MagicMock()
        mock_topics_col.find_one = AsyncMock(return_value=None)
        mock_topics_col.insert_one = AsyncMock()

        with (
            patch("scripts.migrate_sessions_to_topics.sessions_col", return_value=mock_sessions_col),
            patch("scripts.migrate_sessions_to_topics.topics_col", return_value=mock_topics_col),
        ):
            result = await migrate_sessions()

        assert result["migrated"] == 1
        assert result["skipped_empty"] == 0
        assert result["skipped_existing"] == 0
        mock_topics_col.insert_one.assert_called_once()

    @pytest.mark.asyncio
    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    async def test_skips_session_with_zero_messages(self, mock_count):
        session = _make_session(session_id="sess-empty", messages=[])

        mock_sessions_col = MagicMock()
        mock_sessions_col.find.return_value.to_list = AsyncMock(return_value=[session])

        mock_topics_col = MagicMock()
        mock_topics_col.find_one = AsyncMock(return_value=None)
        mock_topics_col.insert_one = AsyncMock()

        with (
            patch("scripts.migrate_sessions_to_topics.sessions_col", return_value=mock_sessions_col),
            patch("scripts.migrate_sessions_to_topics.topics_col", return_value=mock_topics_col),
        ):
            result = await migrate_sessions()

        assert result["skipped_empty"] == 1
        assert result["migrated"] == 0
        mock_topics_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    async def test_skips_already_migrated_session(self, mock_count):
        session = _make_session(
            session_id="sess-already",
            messages=[_make_message()],
        )

        mock_sessions_col = MagicMock()
        mock_sessions_col.find.return_value.to_list = AsyncMock(return_value=[session])

        mock_topics_col = MagicMock()
        # Simulate that a topic already exists with this migratedFrom value
        mock_topics_col.find_one = AsyncMock(return_value={"topicId": "existing-topic"})
        mock_topics_col.insert_one = AsyncMock()

        with (
            patch("scripts.migrate_sessions_to_topics.sessions_col", return_value=mock_sessions_col),
            patch("scripts.migrate_sessions_to_topics.topics_col", return_value=mock_topics_col),
        ):
            result = await migrate_sessions()

        assert result["skipped_existing"] == 1
        assert result["migrated"] == 0
        mock_topics_col.insert_one.assert_not_called()

    @pytest.mark.asyncio
    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    async def test_handles_error_per_session_gracefully(self, mock_count):
        good_session = _make_session(
            session_id="sess-good",
            messages=[_make_message()],
        )
        bad_session = _make_session(
            session_id="sess-bad",
            messages=[_make_message()],
        )

        mock_sessions_col = MagicMock()
        mock_sessions_col.find.return_value.to_list = AsyncMock(
            return_value=[bad_session, good_session]
        )

        call_count = {"find_one": 0}

        async def mock_find_one(query):
            call_count["find_one"] += 1
            if call_count["find_one"] == 1:
                raise RuntimeError("DB error")
            return None

        mock_topics_col = MagicMock()
        mock_topics_col.find_one = mock_find_one
        mock_topics_col.insert_one = AsyncMock()

        with (
            patch("scripts.migrate_sessions_to_topics.sessions_col", return_value=mock_sessions_col),
            patch("scripts.migrate_sessions_to_topics.topics_col", return_value=mock_topics_col),
        ):
            result = await migrate_sessions()

        # First session errored, second migrated successfully
        assert result["errors"] == 1
        assert result["migrated"] == 1

    @pytest.mark.asyncio
    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    async def test_mentor_role_normalized_in_migrated_messages(self, mock_count):
        session = _make_session(
            session_id="sess-mentor",
            messages=[
                _make_message(role="user", content="Question"),
                _make_message(role="mentor", content="Answer from mentor"),
            ],
        )

        mock_sessions_col = MagicMock()
        mock_sessions_col.find.return_value.to_list = AsyncMock(return_value=[session])

        inserted_doc = {}

        async def capture_insert(doc):
            inserted_doc.update(doc)

        mock_topics_col = MagicMock()
        mock_topics_col.find_one = AsyncMock(return_value=None)
        mock_topics_col.insert_one = capture_insert

        with (
            patch("scripts.migrate_sessions_to_topics.sessions_col", return_value=mock_sessions_col),
            patch("scripts.migrate_sessions_to_topics.topics_col", return_value=mock_topics_col),
        ):
            await migrate_sessions()

        # Verify mentor role was normalized to assistant
        assert inserted_doc["messages"][0]["role"] == "user"
        assert inserted_doc["messages"][1]["role"] == "assistant"

    @pytest.mark.asyncio
    @patch("scripts.migrate_sessions_to_topics.count_tokens", return_value=5)
    async def test_mixed_sessions_batch(self, mock_count):
        """Test a batch with empty, already-migrated, and valid sessions."""
        empty_session = _make_session(session_id="sess-empty", messages=[])
        valid_session = _make_session(
            session_id="sess-valid",
            title="Valid Session",
            messages=[_make_message()],
        )
        already_migrated = _make_session(
            session_id="sess-migrated",
            messages=[_make_message()],
        )

        mock_sessions_col = MagicMock()
        mock_sessions_col.find.return_value.to_list = AsyncMock(
            return_value=[empty_session, valid_session, already_migrated]
        )

        async def mock_find_one(query):
            session_id = query.get("migratedFrom")
            if session_id == "sess-migrated":
                return {"topicId": "existing"}
            return None

        mock_topics_col = MagicMock()
        mock_topics_col.find_one = mock_find_one
        mock_topics_col.insert_one = AsyncMock()

        with (
            patch("scripts.migrate_sessions_to_topics.sessions_col", return_value=mock_sessions_col),
            patch("scripts.migrate_sessions_to_topics.topics_col", return_value=mock_topics_col),
        ):
            result = await migrate_sessions()

        assert result["migrated"] == 1
        assert result["skipped_empty"] == 1
        assert result["skipped_existing"] == 1
        assert result["errors"] == 0
