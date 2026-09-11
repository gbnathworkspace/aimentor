"""Unit tests for app/services/llm_trace.py."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_trace import TEXT_CHAR_LIMIT, traced_messages_create, write_trace


def _mock_col():
    col = MagicMock()
    col.insert_one = AsyncMock()
    return col


class TestWriteTrace:
    @pytest.mark.asyncio
    async def test_truncates_prompt_and_response(self):
        col = _mock_col()
        long_text = "x" * (TEXT_CHAR_LIMIT + 50)
        with patch("app.services.llm_trace.llm_traces_col", return_value=col):
            await write_trace(
                "site", "model", "u1", long_text,
                response=long_text, error=None, duration_ms=5,
            )

        doc = col.insert_one.call_args[0][0]
        assert doc["prompt"].startswith("x" * TEXT_CHAR_LIMIT)
        assert "truncated" in doc["prompt"]
        assert "truncated" in doc["response"]
        assert doc["call_site"] == "site"
        assert doc["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_none_response_stays_none(self):
        col = _mock_col()
        with patch("app.services.llm_trace.llm_traces_col", return_value=col):
            await write_trace("site", "", None, "p", response=None, error="boom", duration_ms=1)

        doc = col.insert_one.call_args[0][0]
        assert doc["response"] is None
        assert doc["error"] == "boom"

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self):
        with patch("app.services.llm_trace.llm_traces_col", side_effect=RuntimeError("Database not connected")):
            await write_trace("site", "", None, "p", response="r", error=None, duration_ms=1)


class TestTracedMessagesCreate:
    @pytest.mark.asyncio
    async def test_writes_one_truncated_trace(self):
        col = _mock_col()
        long_text = "y" * (TEXT_CHAR_LIMIT + 10)
        response = SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=response)

        with patch("app.services.llm_trace.llm_traces_col", return_value=col):
            result = await traced_messages_create(
                client, call_site="site", user_id="u1",
                model="m", messages=[{"role": "user", "content": long_text}],
            )

        assert result is response
        col.insert_one.assert_called_once()
        doc = col.insert_one.call_args[0][0]
        assert doc["response"] == "ok"
        assert doc["prompt"].count("truncated") == 1
