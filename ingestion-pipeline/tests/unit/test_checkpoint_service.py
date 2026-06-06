"""Property-based tests for CheckpointService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.checkpoint_service import CheckpointService


# Feature: ingestion-pipeline, Property 19: Checkpoint trigger interval
class TestCheckpointTriggerInterval:
    """Property 19: Checkpoint trigger interval.

    Triggered iff N > 0 and N % 5 == 0.
    """

    @given(turn_number=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=100)
    def test_checkpoint_triggers_on_multiples_of_five(self, turn_number: int):
        """**Validates: Requirements 10.1**

        Auto-checkpoint triggered if and only if turn N is a positive multiple of 5.
        """
        result = CheckpointService.should_checkpoint(turn_number)
        expected = turn_number > 0 and turn_number % 5 == 0
        assert result == expected, (
            f"should_checkpoint({turn_number}) = {result}, expected {expected}"
        )

    @given(turn_number=st.integers(min_value=-100, max_value=0))
    @settings(max_examples=100)
    def test_non_positive_turns_never_trigger(self, turn_number: int):
        """Non-positive turn numbers never trigger checkpoint."""
        result = CheckpointService.should_checkpoint(turn_number)
        assert result is False


# Feature: ingestion-pipeline, Property 20: Checkpoint correctness
class TestCheckpointCorrectness:
    """Property 20: Checkpoint correctness.

    After checkpoint, transcript == M and last_checkpoint_turn == N.
    """

    @given(
        turn_number=st.integers(min_value=5, max_value=100).filter(lambda n: n % 5 == 0),
        num_messages=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_checkpoint_writes_correct_data(self, turn_number: int, num_messages: int):
        """**Validates: Requirements 10.3, 10.4**

        After checkpoint at turn N with messages M, transcript equals M
        and last_checkpoint_turn equals N.
        """
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(num_messages)]

        mock_collection = AsyncMock()
        service = CheckpointService()

        with patch(
            "app.services.checkpoint_service.get_sessions_collection",
            return_value=mock_collection,
        ):
            await service.auto_checkpoint(
                session_id="session-1",
                turn_number=turn_number,
                messages=messages,
            )

        # Verify the update was called with correct values
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args

        filter_arg = call_args[0][0]
        update_arg = call_args[0][1]

        assert filter_arg == {"session_id": "session-1"}
        assert update_arg["$set"]["transcript"] == messages
        assert update_arg["$set"]["last_checkpoint_turn"] == turn_number


# Feature: ingestion-pipeline, Property 21: Orphaned session query correctness
class TestOrphanedSessionQueryCorrectness:
    """Property 21: Orphaned session query correctness.

    Test the query filter logic — query returns sessions with null ended_at,
    null summary, existing checkpoint data, created within 7 days.
    """

    @given(
        num_orphaned=st.integers(min_value=0, max_value=5),
        num_ended=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_orphaned_query_filter_logic(self, num_orphaned: int, num_ended: int):
        """**Validates: Requirements 12.1**

        The orphaned session query filter correctly identifies sessions with:
        (a) ended_at is null, (b) summary is null, (c) transcript exists,
        (d) created_at within 7 days.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=7)

        # Verify the query structure used by recover_orphaned_sessions
        # We test that the filter passed to find() has the correct shape
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        # find() is a regular method that returns a cursor (not a coroutine)
        mock_collection.find = lambda *args, **kwargs: mock_cursor
        # Store the call args manually
        find_calls = []
        original_find = mock_collection.find
        def capturing_find(*args, **kwargs):
            find_calls.append((args, kwargs))
            return mock_cursor
        mock_collection.find = capturing_find

        mock_settings = AsyncMock()
        mock_settings.LLM_ENDPOINT = "http://test"
        mock_settings.LLM_API_KEY = "test-key"

        service = CheckpointService()

        with patch(
            "app.services.checkpoint_service.get_sessions_collection",
            return_value=mock_collection,
        ), patch(
            "app.services.checkpoint_service.get_settings",
            return_value=mock_settings,
        ):
            await service.recover_orphaned_sessions(user_id="user-1")

        # Verify the query filter was correct
        assert len(find_calls) == 1
        query_filter = find_calls[0][0][0]

        assert query_filter["user_id"] == "user-1"
        assert query_filter["ended_at"] is None
        assert query_filter["summary"] is None
        assert query_filter["transcript"] == {"$exists": True}
        # created_at should have a $gte filter with a datetime within 7 days of now
        assert "$gte" in query_filter["created_at"]
        filter_cutoff = query_filter["created_at"]["$gte"]
        # The cutoff should be approximately 7 days ago (within a second tolerance)
        assert abs((filter_cutoff - cutoff).total_seconds()) < 2
