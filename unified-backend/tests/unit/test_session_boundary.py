"""Unit tests for session_boundary.py — closing a topic's session on
window-close/navigate-away, and closing every topic on logout.

Requirements: 1.3, 1.5, 6.2
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import session_boundary


def _msg(msg_id: str, ts: datetime, role: str = "user") -> dict:
    return {"type": "message", "id": msg_id, "role": role, "timestamp": ts}


class TestCloseSessionForTopic:
    @pytest.mark.asyncio
    async def test_closes_using_last_message_timestamp(self):
        last_ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        topic_doc = {"messages": [_msg("m1", last_ts)]}

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await session_boundary.close_session_for_topic("t1", "u1")

            mock_close.assert_awaited_once_with("t1", "u1", upto_timestamp=last_ts)

    @pytest.mark.asyncio
    async def test_no_messages_is_noop(self):
        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value={"messages": []})
            mock_topics.return_value = mock_col

            await session_boundary.close_session_for_topic("t1", "u1")

            mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_topic_is_noop(self):
        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=None)
            mock_topics.return_value = mock_col

            await session_boundary.close_session_for_topic("t1", "u1")

            mock_close.assert_not_called()


class TestMaybeForceCloseLongSession:
    @pytest.mark.asyncio
    async def test_force_closes_when_uncovered_usage_exceeds_ceiling(self):
        now = datetime.now(timezone.utc)
        topic_doc = {"messages": [_msg("m1", now)], "summaryBlocks": []}

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close, \
             patch.object(
                 session_boundary._token_counter, "get_usage_percent", return_value=61,
             ):
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await session_boundary.maybe_force_close_long_session("t1", "u1", now)

            mock_close.assert_awaited_once_with("t1", "u1", upto_timestamp=now)

    @pytest.mark.asyncio
    async def test_noop_under_ceiling(self):
        now = datetime.now(timezone.utc)
        topic_doc = {"messages": [_msg("m1", now)], "summaryBlocks": []}

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close, \
             patch.object(
                 session_boundary._token_counter, "get_usage_percent", return_value=10,
             ):
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await session_boundary.maybe_force_close_long_session("t1", "u1", now)

            mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_when_everything_already_covered(self):
        now = datetime.now(timezone.utc)
        topic_doc = {
            "messages": [_msg("m1", now)],
            "summaryBlocks": [{"sourceSessionIds": ["m1"]}],
        }

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            await session_boundary.maybe_force_close_long_session("t1", "u1", now)

            mock_close.assert_not_called()


class TestCloseAllSessionsForUser:
    @pytest.mark.asyncio
    async def test_closes_every_open_topic_for_user(self):
        ts = datetime.now(timezone.utc)
        topics = [
            {"topicId": "t1", "messages": [_msg("m1", ts)]},
            {"topicId": "t2", "messages": [_msg("m2", ts)]},
        ]

        async def _aiter():
            for t in topics:
                yield t

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find.return_value = _aiter()
            mock_topics.return_value = mock_col

            await session_boundary.close_all_sessions_for_user("u1")

            assert mock_close.await_count == 2
