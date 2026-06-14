"""Mentor router — POST /api/mentor chat endpoint."""

import logging

import anthropic
from fastapi import APIRouter, Depends

from app.config.database import immediate_contexts_col
from app.config.settings import get_settings
from app.core.security import require_auth
from app.models.chat import MentorRequest, MentorResponse
from app.services import context_assembler
from app.services.prompt_store import get_system_prompt
from app.services.token_budget import (
    ImmediateContextDoc,
    apply_token_budget_priority,
    count_tokens,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mentor", tags=["Mentor"])


@router.post("", response_model=MentorResponse)
async def mentor_chat(
    body: MentorRequest,
    user_id: str = Depends(require_auth),
) -> MentorResponse:
    """Handle a mentor chat request.

    1. Assemble context (L1 profile, L2 skill, L3 episodes) — raises 400 if no profile.
    2. Build system prompt from mode template + context.
    3. If sessionId provided, append ImmediateContext (uploaded file content).
    4. Call Anthropic API with system prompt + user messages.
    5. Return the assistant's text response.
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

    # Step 2: Build system prompt from mode + context
    system_prompt = get_system_prompt(body.mode, context)

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

    # Step 4: Call Anthropic API
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    api_messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=api_messages,
        )
    except Exception:
        logger.exception("Anthropic API call failed for user=%s topic=%s mode=%s", user_id, body.topic, body.mode)
        raise

    # Step 5: Extract and return assistant text
    response_text = response.content[0].text if response.content else ""

    return MentorResponse(text=response_text)
