"""Onboarding router — /api/onboarding/chat + /complete + /skip + /complete-deferred."""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status

from app.config.database import profiles_col, sessions_col
from app.config.settings import get_settings
from app.core.security import require_auth
from app.models.chat import (
    OnboardingCompleteRequest,
    OnboardingCompleteResponse,
    OnboardingCompleteDeferredRequest,
    OnboardingCompleteDeferredResponse,
    OnboardingRequest,
    OnboardingResponse,
    OnboardingSkipRequest,
    OnboardingSkipResponse,
)
from app.services.onboarding_bootstrap import bootstrap_skills
from app.services.prompt_store import get_onboarding_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


def parse_onboarding_response(text: str) -> dict:
    """Parse LLM response for suggestion chips and onboarding_complete blocks."""
    suggestions: list[str] = []
    complete = False
    profile_data = None

    # Extract suggestions block
    suggestions_match = re.search(
        r"```json suggestions\s*\n(.*?)\n```", text, re.DOTALL
    )
    if suggestions_match:
        try:
            suggestions = json.loads(suggestions_match.group(1))
        except json.JSONDecodeError:
            pass

    # Extract onboarding_complete block
    complete_match = re.search(
        r"```json onboarding_complete\s*\n(.*?)\n```", text, re.DOTALL
    )
    if complete_match:
        try:
            profile_data = json.loads(complete_match.group(1))
            complete = True
        except json.JSONDecodeError:
            pass

    # Clean the text (remove the fenced blocks)
    clean_text = re.sub(
        r"```json (?:suggestions|onboarding_complete)\s*\n.*?\n```",
        "",
        text,
        flags=re.DOTALL,
    ).strip()

    return {
        "text": clean_text,
        "suggestions": suggestions,
        "complete": complete,
        "profile_data": profile_data,
    }


@router.post("/chat", response_model=OnboardingResponse)
async def onboarding_chat(
    body: OnboardingRequest,
    user_id: str = Depends(require_auth),
) -> OnboardingResponse:
    """Handle an onboarding chat request.

    1. Load the onboarding system prompt.
    2. Call Anthropic with system prompt + user messages.
    3. Parse the response for suggestion chips and onboarding_complete block.
    4. Return the parsed response.
    """
    settings = get_settings()

    # Load onboarding system prompt
    system_prompt = get_onboarding_prompt()

    # Build API messages
    api_messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            messages=api_messages,
        )

        response_text = response.content[0].text if response.content else ""
    except Exception as e:
        logger.error(f"LLM call failed during onboarding chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM call failed",
        )

    # Parse the LLM response
    parsed = parse_onboarding_response(response_text)

    return OnboardingResponse(
        text=parsed["text"],
        suggestions=parsed["suggestions"],
        complete=parsed["complete"],
        profile=parsed["profile_data"],
    )


@router.post("/complete", response_model=OnboardingCompleteResponse)
async def onboarding_complete(
    body: OnboardingCompleteRequest,
    user_id: str = Depends(require_auth),
) -> OnboardingCompleteResponse:
    """Complete onboarding: upsert L1 profile and bootstrap skill graph.

    1. Upsert the user's L1 profile with the provided data.
    2. Call bootstrap_skills to generate initial skill graph nodes.
    3. Return the list of skill topics created.
    """
    # Upsert L1 profile
    profile_data = {
        "user_id": user_id,
        "goal": body.goal,
        "deadline": body.deadline,
        "overall_level": body.overall_level,
        "daily_availability": body.daily_availability,
        "profile_status": "complete",
    }

    await profiles_col().update_one(
        {"user_id": user_id},
        {"$set": profile_data},
        upsert=True,
    )

    # Bootstrap skills from goal
    skill_nodes = await bootstrap_skills(user_id, body.goal, body.overall_level)

    return OnboardingCompleteResponse(skills=skill_nodes)


_SKIP_DEFAULTS = {
    "goal": "exploring",
    "deadline": None,
    "daily_availability": "1 hour",
    "overall_level": "beginner",
}


@router.post("/skip", response_model=OnboardingSkipResponse)
async def onboarding_skip(
    body: OnboardingSkipRequest,
    user_id: str = Depends(require_auth),
) -> OnboardingSkipResponse:
    """Skip onboarding: create a minimal profile and a new chat session."""
    partial = body.partial_profile or {}

    profile_data = {
        "user_id": user_id,
        "goal": partial.get("goal") or _SKIP_DEFAULTS["goal"],
        "deadline": partial.get("deadline") or _SKIP_DEFAULTS["deadline"],
        "daily_availability": partial.get("daily_availability") or _SKIP_DEFAULTS["daily_availability"],
        "overall_level": partial.get("overall_level") or _SKIP_DEFAULTS["overall_level"],
        "email": "",
        "profile_status": "skipped",
    }

    await profiles_col().update_one(
        {"user_id": user_id},
        {"$set": profile_data},
        upsert=True,
    )

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await sessions_col().insert_one({
        "session_id": session_id,
        "user_id": user_id,
        "title": "New session",
        "mode": "topic",
        "status": "active",
        "messages": [],
        "tags": [],
        "created_at": now,
        "updated_at": now,
    })

    return OnboardingSkipResponse(ok=True, session_id=session_id)


@router.post("/complete-deferred", response_model=OnboardingCompleteDeferredResponse)
async def onboarding_complete_deferred(
    body: OnboardingCompleteDeferredRequest,
    user_id: str = Depends(require_auth),
) -> OnboardingCompleteDeferredResponse:
    """Complete deferred onboarding: merge new answers and set profile_status to complete."""
    existing = await profiles_col().find_one({"user_id": user_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile found. Please complete full onboarding.",
        )

    updates: dict = {"profile_status": "complete"}
    if body.goal:
        updates["goal"] = body.goal
    if body.deadline is not None:
        updates["deadline"] = body.deadline
    if body.overall_level:
        updates["overall_level"] = body.overall_level
    if body.daily_availability:
        updates["daily_availability"] = body.daily_availability

    await profiles_col().update_one({"user_id": user_id}, {"$set": updates})

    return OnboardingCompleteDeferredResponse(ok=True)
