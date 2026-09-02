"""Tracing wrapper around anthropic.AsyncAnthropic().messages.create(...).

Every LLM call site in this backend should go through traced_messages_create
instead of calling client.messages.create directly, so the admin /analytics
view (see app/auth/admin_router.py::list_traces) has something to show.
Writes are best-effort — a tracing failure must never break the LLM call it
wraps, same convention as skill_graph_repo.apply_update.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.config.database import llm_traces_col

logger = logging.getLogger(__name__)

TEXT_CHAR_LIMIT = 4000  # caps both prompt and response text stored per trace


def _truncate(text: str) -> str:
    if len(text) <= TEXT_CHAR_LIMIT:
        return text
    return text[:TEXT_CHAR_LIMIT] + f"… [truncated, {len(text)} chars total]"


def _extract_prompt_text(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.append("".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            ))
    return _truncate("\n\n".join(parts))


def _extract_response_text(response: Any) -> str:
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    return _truncate(text)


async def traced_messages_create(client, *, call_site: str, user_id: str | None = None, **kwargs):
    """Call client.messages.create(**kwargs), persisting a trace either way.

    Args:
        client: an anthropic.AsyncAnthropic instance.
        call_site: identifies where this call came from, e.g.
            "subtopic_weights._score_proficiency_llm" — shown in the trace list.
        user_id: the user this call is on behalf of, or None for calls not
            scoped to a single user (e.g. topic decomposition, cached per-topic).
        **kwargs: forwarded as-is to client.messages.create.
    """
    prompt = _extract_prompt_text(kwargs.get("messages", []))
    start = time.monotonic()
    try:
        response = await client.messages.create(**kwargs)
    except Exception as e:
        await _write_trace(
            call_site, kwargs.get("model", ""), user_id, prompt,
            response=None, error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        raise

    await _write_trace(
        call_site, kwargs.get("model", ""), user_id, prompt,
        response=_extract_response_text(response), error=None,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    return response


async def _write_trace(
    call_site: str, model: str, user_id: str | None, prompt: str,
    *, response: str | None, error: str | None, duration_ms: int,
) -> None:
    try:
        await llm_traces_col().insert_one({
            "call_site": call_site,
            "model": model,
            "user_id": user_id,
            "prompt": prompt,
            "response": response,
            "error": error,
            "duration_ms": duration_ms,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error("Failed to write LLM trace for call_site=%s: %s", call_site, str(e))
