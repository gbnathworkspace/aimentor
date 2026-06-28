"""Mentor router — POST /api/mentor chat endpoint."""

import logging

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config.database import immediate_contexts_col
from app.config.settings import get_settings
from app.core.security import require_auth
from app.models.chat import MentorRequest
from app.services import context_assembler
from app.services.prompt_store import get_system_prompt
from app.services.token_budget import (
    ImmediateContextDoc,
    apply_token_budget_priority,
    count_tokens,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mentor", tags=["Mentor"])

# Cap the chat history sent to the LLM. Without this the full transcript is
# re-sent every turn → O(n²) token cost and eventual context overflow (issue #15).
# Older turns survive across sessions via L3 summaries.
_MAX_HISTORY_MESSAGES = 20


def _window_messages(messages: list, limit: int = _MAX_HISTORY_MESSAGES) -> list[dict]:
    """Keep the last `limit` messages, then drop leading assistant turns.

    Anthropic requires the first message to be 'user'; slicing the tail can start
    on an assistant turn, so trim until the first user message.
    """
    windowed = messages[-limit:]
    first_user = next(
        (i for i, m in enumerate(windowed) if m.role == "user"), len(windowed)
    )
    windowed = windowed[first_user:]
    return [{"role": m.role, "content": m.content} for m in windowed]


@router.post("")
async def mentor_chat(
    body: MentorRequest,
    user_id: str = Depends(require_auth),
) -> StreamingResponse:
    """Handle a mentor chat request, streaming the reply token-by-token (issue #17).

    1. Assemble context (L1 profile, L2 skill, L3 episodes) — raises 400 if no profile.
    2. Build system prompt from mode template + context.
    3. If sessionId provided, append ImmediateContext (uploaded file content).
    4. Stream the assistant's reply as plain-text chunks via Anthropic's stream API.
    """
    settings = get_settings()

    # Determine last user message for vector search query
    last_user_message = ""
    for msg in reversed(body.messages):
        if msg.role == "user":
            last_user_message = msg.content
            break

    # Step 1: Assemble context (raises HTTPException 400 if no profile)
    context = await context_assembler.assemble(user_id, body.topic, last_user_message)

    # Step 2: Build system prompt from mode + context.
    # MentorRequest already constrains `mode` to the known set, but guard the
    # internal contract too so a bad mode can never crash the core chat (issue #6).
    try:
        system_prompt = get_system_prompt(body.mode, context, body.tone)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    # Step 3: If sessionId provided, include ImmediateContext from uploaded files
    if body.session_id:
        immediate_ctx = await immediate_contexts_col().find_one(
            {"session_id": body.session_id, "user_id": user_id},
            {"_id": 0},
        )
        if immediate_ctx and immediate_ctx.get("blocks"):
            blocks = immediate_ctx["blocks"]  # oldest-first
            # Token budget priority: core context (system prompt) is never dropped;
            # uploaded-file blocks are trimmed oldest-first to fit the budget.
            docs = [
                ImmediateContextDoc(
                    job_id=str(i),
                    token_count=count_tokens(block.get("content", "")),
                )
                for i, block in enumerate(blocks)
            ]
            budget = apply_token_budget_priority(
                docs,
                core_context_tokens=count_tokens(system_prompt),
                episodic_rag_tokens=0,
            )
            included_indices = {int(d.job_id) for d in budget.included_docs}
            file_context_parts = [
                f"--- Uploaded File: {block.get('filename', 'Unknown file')} ---\n"
                f"{block.get('content', '')}"
                for i, block in enumerate(blocks)
                if i in included_indices
            ]
            if budget.budget_exceeded:
                logger.info(
                    "ImmediateContext trimmed for session=%s: kept %d/%d file blocks",
                    body.session_id,
                    len(included_indices),
                    len(blocks),
                )
            if file_context_parts:
                file_section = (
                    "\n\n## Uploaded File Context\n\n"
                    + "\n\n".join(file_context_parts)
                )
                system_prompt += file_section

    # Step 4: Stream the assistant reply as plain-text chunks.
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    api_messages = _window_messages(body.messages)

    async def token_stream():
        try:
            async with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=api_messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception:
            # The stream has already started (200 sent), so we can't switch to a
            # 500 — emit a visible marker the client appends, and log for triage.
            logger.exception(
                "Anthropic stream failed for user=%s topic=%s mode=%s",
                user_id, body.topic, body.mode,
            )
            yield "\n\n[error: the mentor response was interrupted — please try again]"

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")
