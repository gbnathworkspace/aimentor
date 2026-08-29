"""Unit tests for session_boundary.py — gap detection, idle sweep, logout.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import session_boundary


def _msg(msg_id: str, ts: datetime, role: str = "user") -> dict:
    return {"type": "message", "id": msg_id, "role": role, "timestamp": ts}


class TestCheckAndCloseOnNewMessage:
    @pytest.mark.asyncio
    async def test_gap_under_threshold_does_not_close(self):
        last_ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        topic_doc = {"messages": [_msg("m1", last_ts)]}

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            new_ts = last_ts + timedelta(minutes=5)
            await session_boundary.check_and_close_on_new_message("t1", "u1", new_ts)

            mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_gap_over_threshold_closes(self):
        last_ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        topic_doc = {"messages": [_msg("m1", last_ts)]}

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            new_ts = last_ts + timedelta(minutes=11)
            await session_boundary.check_and_close_on_new_message("t1", "u1", new_ts)

            mock_close.assert_awaited_once_with("t1", "u1", upto_timestamp=last_ts)

    @pytest.mark.asyncio
    async def test_gap_measured_role_agnostic(self):
        """Gap is measured against the last message regardless of role (Req 1.4)."""
        last_ts = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        topic_doc = {"messages": [_msg("m1", last_ts, role="assistant")]}

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find_one = AsyncMock(return_value=topic_doc)
            mock_topics.return_value = mock_col

            new_ts = last_ts + timedelta(minutes=11)
            await session_boundary.check_and_close_on_new_message("t1", "u1", new_ts)

            mock_close.assert_awaited_once_with("t1", "u1", upto_timestamp=last_ts)


class TestIdleSweep:
    @pytest.mark.asyncio
    async def test_closes_stale_topic_with_no_next_message(self):
        last_ts = datetime.now(timezone.utc) - timedelta(minutes=20)
        stale_topic = {"topicId": "t1", "userId": "u1", "messages": [_msg("m1", last_ts)]}

        async def _aiter():
            yield stale_topic

        with patch("app.services.session_boundary.topics_col") as mock_topics, \
             patch("app.services.session_boundary.close_session", new=AsyncMock()) as mock_close:
            mock_col = MagicMock()
            mock_col.find.return_value = _aiter()
            mock_topics.return_value = mock_col

            closed = await session_boundary.idle_sweep()

            assert closed == 1
            mock_close.assert_awaited_once_with("t1", "u1", upto_timestamp=last_ts)


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
