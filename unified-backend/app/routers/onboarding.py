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
from app.auth.dependencies import require_auth
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
from app.models.profile import LearningContext, LearningContextDetail, ProfileCreate
from app.services.onboarding_bootstrap import bootstrap_skills
from app.services.prompt_store import get_onboarding_prompt
from app.services.response_parsing import extract_suggestions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


def parse_onboarding_response(text: str) -> dict:
    """Parse LLM response for suggestion chips and onboarding_complete blocks."""
    clean_text, suggestions = extract_suggestions(text)
    complete = False
    profile_data = None

    # Extract onboarding_complete block
    complete_match = re.search(
        r"```json onboarding_complete\s*\n(.*?)\n```", clean_text, re.DOTALL
    )
    if complete_match:
        try:
            profile_data = json.loads(complete_match.group(1))
            complete = True
        except json.JSONDecodeError:
            pass

    # Clean the onboarding_complete block out too
    clean_text = re.sub(
        r"```json onboarding_complete\s*\n.*?\n```",
        "",
        clean_text,
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
    # Build via ProfileCreate so the write always matches the L1 schema.
    profile_model = ProfileCreate(
        learning_context=body.learning_context,
        learning_context_detail=(
            LearningContextDetail(
                learning_context=body.learning_context,
                situations=[body.learning_context_label],
            )
            if body.learning_context_label
            else None
        ),
        focus_areas=body.focus_areas,
        explanation_style=body.explanation_style,
        challenge_tolerance=body.challenge_tolerance,
        feedback_tone=body.feedback_tone,
        profile_status="complete",
    )
    profile_data = profile_model.model_dump(mode="json", exclude_none=True)
    profile_data["user_id"] = user_id

    await profiles_col().update_one(
        {"user_id": user_id},
        {"$set": profile_data},
        upsert=True,
    )

    # Bootstrap skills from focus areas (falls back to the context label)
    skill_nodes = await bootstrap_skills(
        user_id, body.focus_areas, body.learning_context_label
    )

    return OnboardingCompleteResponse(skills=skill_nodes)


_SKIP_DEFAULTS = {
    "learning_context": LearningContext.SELF_DIRECTED.value,
    "focus_areas": [],
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
        "learning_context": partial.get("learning_context") or _SKIP_DEFAULTS["learning_context"],
        "focus_areas": partial.get("focus_areas") or _SKIP_DEFAULTS["focus_areas"],
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
    resolved_context = body.learning_context or existing.get("learning_context")
    if body.learning_context is not None:
        updates["learning_context"] = body.learning_context.value
    if body.learning_context_label is not None and resolved_context:
        existing_detail = existing.get("learning_context_detail") or {}
        prior_situations = [
            s for s in (existing_detail.get("situations") or [])
            if s != body.learning_context_label
        ]
        updates["learning_context_detail"] = {
            "learning_context": (
                body.learning_context.value
                if body.learning_context
                else resolved_context
            ),
            "contexts": existing_detail.get("contexts") or [],
            "situations": [body.learning_context_label, *prior_situations][:20],
        }
    if body.focus_areas is not None:
        updates["focus_areas"] = body.focus_areas
    if body.explanation_style is not None:
        updates["explanation_style"] = body.explanation_style
    if body.challenge_tolerance is not None:
        updates["challenge_tolerance"] = body.challenge_tolerance
    if body.feedback_tone is not None:
        updates["feedback_tone"] = body.feedback_tone

    await profiles_col().update_one({"user_id": user_id}, {"$set": updates})

    return OnboardingCompleteDeferredResponse(ok=True)
