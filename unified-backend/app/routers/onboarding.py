"""Onboarding router — /api/onboarding/chat + /complete."""

import json
import logging
import re

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status

from app.config.database import profiles_col
from app.config.settings import get_settings
from app.core.security import require_auth
from app.models.chat import (
    OnboardingCompleteRequest,
    OnboardingCompleteResponse,
    OnboardingRequest,
    OnboardingResponse,
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
    }

    await profiles_col().update_one(
        {"user_id": user_id},
        {"$set": profile_data},
        upsert=True,
    )

    # Bootstrap skills from goal
    skill_nodes = await bootstrap_skills(user_id, body.goal, body.overall_level)

    return OnboardingCompleteResponse(skills=skill_nodes)
