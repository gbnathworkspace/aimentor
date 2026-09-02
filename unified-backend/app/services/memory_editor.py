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
from app.models.profile import StyleNoteCategory
from app.services.llm_trace import traced_messages_create

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {c.value for c in StyleNoteCategory}

_FALLBACK_SUMMARY = "Couldn't match that to anything in your profile — try being more specific."


def _build_prompt(profile: dict[str, Any], message: str) -> str:
    existing_detail = profile.get("learning_context_detail") or {}
    situations = existing_detail.get("situations") or []
    current = {
        "learning_context_label": existing_detail.get("label"),
        "situations": [{"index": i, "text": s} for i, s in enumerate(situations)],
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
        '  "learning_context_label": string\n'
        '  "add_situation": string — a new fact to add to "Facts About You"\n'
        '  "remove_situation_indices": array of integers — indices from situations above to delete\n'
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
        response = await traced_messages_create(
            client, call_site="memory_editor._call_llm",
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

    existing_detail = profile.get("learning_context_detail") or {}
    situations = list(existing_detail.get("situations") or [])
    label = existing_detail.get("label")
    detail_changed = False

    if isinstance(data.get("learning_context_label"), str):
        label = data["learning_context_label"]
        situations = [s for s in situations if s != label]
        situations = [label, *situations]
        detail_changed = True

    remove_situation_indices = data.get("remove_situation_indices")
    if isinstance(remove_situation_indices, list) and remove_situation_indices and all(
        isinstance(i, int) for i in remove_situation_indices
    ):
        drop = set(remove_situation_indices)
        situations = [s for i, s in enumerate(situations) if i not in drop]
        detail_changed = True

    add_situation = data.get("add_situation")
    if isinstance(add_situation, str) and add_situation.strip():
        situations = [add_situation.strip(), *situations]
        detail_changed = True

    if detail_changed:
        update["learning_context_detail"] = {
            "label": label,
            "situations": situations[:20],
        }

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
