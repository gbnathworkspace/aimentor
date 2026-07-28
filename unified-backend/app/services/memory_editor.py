"""Direct natural-language editing of L1 memory (the Settings > Memory chat box).

Unlike app/services/profiling_agent.py — which proposes inferred changes that
sit in pending_changes until accepted — this is user-authored: the user typed
the instruction themselves in Settings, so it applies immediately. Same trust
level as editing a form field directly; no accept/dismiss gate.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import anthropic

from app.config.database import profiles_col
from app.config.settings import get_settings
from app.models.profile import LearningContext, StyleNoteCategory

logger = logging.getLogger(__name__)

_VALID_CONTEXTS = {c.value for c in LearningContext}
_VALID_CATEGORIES = {c.value for c in StyleNoteCategory}
_VALID_EXPLANATION = {"hint-first", "answer-first"}
_VALID_CHALLENGE = {"low", "medium", "high"}
_VALID_TONE = {"direct", "encouraging"}

_FALLBACK_SUMMARY = "Couldn't match that to anything in your profile — try being more specific."


def _build_prompt(profile: dict[str, Any], message: str) -> str:
    current = {
        "learning_context": profile.get("learning_context"),
        "learning_context_label": (profile.get("learning_context_detail") or {}).get("label"),
        "focus_areas": profile.get("focus_areas") or [],
        "explanation_style": profile.get("explanation_style", "hint-first"),
        "challenge_tolerance": profile.get("challenge_tolerance", "medium"),
        "feedback_tone": profile.get("feedback_tone", "encouraging"),
        "style_notes": [
            {"index": i, "category": n.get("category"), "note": n.get("note")}
            for i, n in enumerate(profile.get("style_notes") or [])
        ],
    }
    return (
        "You edit a user's learning-mentor profile based on their direct instruction. "
        "Only change what they explicitly ask for — omit every other key.\n\n"
        f"Current profile:\n{json.dumps(current, indent=2)}\n\n"
        f'User\'s instruction: "{message}"\n\n'
        "Respond with ONLY a JSON object (no markdown, no explanation). Every key is "
        "optional — include a key ONLY if the instruction changes it:\n"
        '  "learning_context": one of job_interview|high_stakes_exam|competitive_test|self_directed|other\n'
        '  "learning_context_label": string\n'
        '  "focus_areas": array of strings — the FULL replacement list, only if focus areas are being changed\n'
        '  "explanation_style": hint-first|answer-first\n'
        '  "challenge_tolerance": low|medium|high\n'
        '  "feedback_tone": direct|encouraging\n'
        '  "remove_style_note_indices": array of integers — indices from style_notes above to delete\n'
        '  "add_style_note": {"category": pacing|communication|motivation|misconception|context, "note": "short claim"}\n'
        '  "summary": one short sentence describing what you changed, shown to the user\n\n'
        "If the instruction doesn't map to anything above, or is unclear, respond with exactly "
        '{"summary": "' + _FALLBACK_SUMMARY + '"} and no other keys.'
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from LLM output, tolerating markdown code fences
    (Haiku sometimes wraps JSON in ```json ... ``` despite instructions)."""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


async def _call_llm(prompt: str) -> dict[str, Any] | None:
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        data = _extract_json(text)
        if data is None:
            logger.warning("Memory edit response had no parseable JSON: %r", text[:300])
        return data
    except Exception as e:
        logger.warning("Memory edit LLM call failed: %s", str(e))
        return None


async def apply_memory_edit(user_id: str, message: str) -> dict[str, Any]:
    """Interpret a free-text instruction against the user's current L1 profile
    and apply it directly. Returns {"summary": str, "changed": bool}.

    Never raises — returns changed=False with an explanatory summary on any
    LLM/parse failure, matching the rest of the profile-write error handling.
    """
    profile = await profiles_col().find_one({"user_id": user_id}) or {}
    data = await _call_llm(_build_prompt(profile, message))
    if data is None:
        return {"summary": "Something went wrong understanding that — try again.", "changed": False}

    update: dict[str, Any] = {}

    if data.get("learning_context") in _VALID_CONTEXTS:
        update["learning_context"] = data["learning_context"]

    if isinstance(data.get("learning_context_label"), str):
        ctx = update.get("learning_context") or profile.get("learning_context") or "self_directed"
        existing_detail = profile.get("learning_context_detail") or {}
        label = data["learning_context_label"]
        situations = [s for s in (existing_detail.get("situations") or []) if s != label]
        update["learning_context_detail"] = {
            "learning_context": ctx,
            "contexts": existing_detail.get("contexts") or [ctx],
            "label": label,
            # The new label joins the injected list rather than replacing it —
            # this write used to drop `situations` entirely.
            "situations": [label, *situations][:20],
        }

    if isinstance(data.get("focus_areas"), list) and all(isinstance(x, str) for x in data["focus_areas"]):
        update["focus_areas"] = data["focus_areas"]

    if data.get("explanation_style") in _VALID_EXPLANATION:
        update["explanation_style"] = data["explanation_style"]
    if data.get("challenge_tolerance") in _VALID_CHALLENGE:
        update["challenge_tolerance"] = data["challenge_tolerance"]
    if data.get("feedback_tone") in _VALID_TONE:
        update["feedback_tone"] = data["feedback_tone"]

    style_notes = list(profile.get("style_notes") or [])
    style_notes_changed = False

    remove_indices = data.get("remove_style_note_indices")
    if isinstance(remove_indices, list) and remove_indices and all(isinstance(i, int) for i in remove_indices):
        drop = set(remove_indices)
        style_notes = [n for i, n in enumerate(style_notes) if i not in drop]
        style_notes_changed = True

    add_note = data.get("add_style_note")
    if isinstance(add_note, dict) and add_note.get("category") in _VALID_CATEGORIES and add_note.get("note"):
        style_notes.append({
            "category": add_note["category"],
            "note": str(add_note["note"])[:140],
            "source_quote": message[:200],
            "session_id": "manual-edit",
            "added_at": datetime.now(timezone.utc).isoformat(),
        })
        # ponytail: same FIFO cap as the accept-a-proposal path in routers/profile.py
        style_notes = style_notes[-5:]
        style_notes_changed = True

    if style_notes_changed:
        update["style_notes"] = style_notes

    summary = data.get("summary") or "Updated."
    if not update:
        return {"summary": summary, "changed": False}

    await profiles_col().update_one({"user_id": user_id}, {"$set": update})
    return {"summary": summary, "changed": True}
