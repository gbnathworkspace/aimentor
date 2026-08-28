"""Profile router — /api/profile CRUD."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.config.database import profiles_col, users_col
from app.auth.dependencies import require_auth
from app.models.profile import ProfileCreate, ProfileResponse, ProfileUpdate, ProposableField
from app.services.avatar_storage import delete_avatar, resolve_avatar_url, store_avatar
from app.services.fact_quality import classify_fact_quality, compute_situations_stamp
from app.services.memory_editor import apply_memory_edit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profile", tags=["Profile"])

# Cap on the incoming upload (a data URI the client always sends); the value
# actually persisted may be much smaller (an S3 key) — see avatar_storage.py.
MAX_AVATAR_CHARS = 2_800_000  # ~2MB image, base64-inflated


def _validate_avatar(avatar: str | None) -> None:
    if not avatar:  # None or "" (empty string clears the avatar)
        return
    if not avatar.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Avatar must be an image data URI")
    if len(avatar) > MAX_AVATAR_CHARS:
        raise HTTPException(status_code=400, detail="Avatar image is too large (max ~2MB)")


async def _get_avatar(user_id: str) -> str | None:
    user = await users_col().find_one({"user_id": user_id}, {"avatar": 1})
    return resolve_avatar_url((user or {}).get("avatar"))


async def _set_avatar(user_id: str, data_uri: str | None) -> str | None:
    """Store an incoming avatar upload (or clear it) and return the URL to
    hand back to the client immediately. Deletes the previous S3 object,
    if any, when replacing or clearing."""
    previous = (await users_col().find_one({"user_id": user_id}, {"avatar": 1}) or {}).get("avatar")
    if not data_uri:
        if previous:
            delete_avatar(previous)
        await users_col().update_one({"user_id": user_id}, {"$set": {"avatar": None}})
        return None

    stored = store_avatar(user_id, data_uri)
    if previous and previous != stored:
        delete_avatar(previous)
    await users_col().update_one({"user_id": user_id}, {"$set": {"avatar": stored}})
    return resolve_avatar_url(stored)


@router.get("", response_model=ProfileResponse)
async def get_profile(user_id: str = Depends(require_auth)):
    """Return the L1 profile for the authenticated user."""
    doc = await profiles_col().find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")
    return doc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProfileResponse)
async def create_profile(
    data: ProfileCreate, user_id: str = Depends(require_auth)
):
    """Create a new profile for the authenticated user."""
    doc = data.model_dump()
    doc["user_id"] = user_id
    try:
        await profiles_col().insert_one(doc)
    except DuplicateKeyError:
        logger.warning("Duplicate profile creation attempt for user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists for this user",
        )
    except Exception:
        logger.exception("Failed to create profile for user=%s", user_id)
        raise
    doc.pop("_id", None)
    return doc


@router.put("", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdate, user_id: str = Depends(require_auth)
):
    """Update the profile for the authenticated user."""
    update_data = data.model_dump(exclude_none=True)

    if not update_data:
        # Nothing to update — just return current state
        doc = await profiles_col().find_one({"user_id": user_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Profile not found")
        return doc

    result = await profiles_col().find_one_and_update(
        {"user_id": user_id},
        {"$set": update_data},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Profile not found")
    result.pop("_id", None)
    return result


class AvatarUpdateRequest(BaseModel):
    """Request body for PUT /api/profile/avatar. `avatar` is a data URI
    (data:image/...;base64,...) to set, or None/empty to clear."""

    avatar: Optional[str] = None


@router.get("/avatar")
async def get_avatar(user_id: str = Depends(require_auth)):
    """Return the resolved avatar URL, if any. Stored on the `users` doc,
    not `profiles` — see _get_avatar/_set_avatar above."""
    return {"avatar": await _get_avatar(user_id)}


@router.put("/avatar")
async def set_avatar(body: AvatarUpdateRequest, user_id: str = Depends(require_auth)):
    """Set or clear (empty/None) the authenticated user's avatar."""
    _validate_avatar(body.avatar)
    return {"avatar": await _set_avatar(user_id, body.avatar)}


@router.delete("")
async def delete_profile(user_id: str = Depends(require_auth)):
    """Delete the L1 profile for the authenticated user. Skill graph (L2) and
    session history (L3) are untouched — this resets learning context, focus
    areas, preferences, style notes, and pending changes only."""
    result = await profiles_col().delete_one({"user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"ok": True}


@router.get("/situations/quality")
async def get_situations_quality(user_id: str = Depends(require_auth)):
    """Judge each "Facts About You" entry: does it actually state a fact
    about the user, or just name a topic/skill (see fact_quality.py)?

    Cached on the profile doc, keyed by a stamp of the situations list
    (same pattern as TopicService._ensure_l1_scope) — the LLM is only
    called again when a fact was added, edited, or removed since the last
    judgment, not on every Settings open.
    """
    doc = await profiles_col().find_one(
        {"user_id": user_id},
        {"learning_context_detail": 1, "situation_quality": 1, "situationQualityStamp": 1},
    )
    situations = ((doc or {}).get("learning_context_detail") or {}).get("situations") or []
    current_stamp = compute_situations_stamp(situations)

    if doc and doc.get("situationQualityStamp") == current_stamp and "situation_quality" in doc:
        return {"judgments": doc["situation_quality"]}

    try:
        judgments = await classify_fact_quality(situations)
    except Exception:
        logger.exception("classify_fact_quality failed for user_id=%s", user_id)
        return {"judgments": []}

    await profiles_col().update_one(
        {"user_id": user_id},
        {"$set": {"situation_quality": judgments, "situationQualityStamp": current_stamp}},
    )
    return {"judgments": judgments}


def _find_pending(doc: dict, field: str) -> dict | None:
    return next((p for p in doc.get("pending_changes", []) if p.get("field") == field), None)


@router.post("/pending-changes/{field}/accept", response_model=ProfileResponse)
async def accept_pending_change(field: str, user_id: str = Depends(require_auth)):
    """Apply a pending profile-agent proposal and remove it from the queue.

    See app/services/profiling_agent.py — proposals are never auto-applied;
    this is the only path that writes them into the live profile.
    """
    if field not in {f.value for f in ProposableField}:
        raise HTTPException(status_code=400, detail="Unknown field")

    doc = await profiles_col().find_one({"user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")

    change = _find_pending(doc, field)
    if not change:
        raise HTTPException(status_code=404, detail="No pending change for this field")

    proposed = change["proposed_value"]
    update: dict = {}

    if field == ProposableField.STYLE_NOTE.value:
        new_note = {
            "category": proposed["category"],
            "note": proposed["note"],
            "source_quote": change.get("reason", ""),
            "session_id": change.get("session_id", ""),
            "added_at": change.get("created_at"),
        }
        # ponytail: FIFO drop-oldest past the 5-note cap. Good enough since every
        # addition is user-confirmed already; add relevance scoring if a dropped
        # note turns out to matter more than a newer one.
        notes = (doc.get("style_notes") or []) + [new_note]
        update["style_notes"] = notes[-5:]
    elif field == ProposableField.SITUATION.value:
        detail = dict(doc.get("learning_context_detail") or {})
        situations = list(detail.get("situations") or [])
        new_situation = proposed.get("value", "")
        # Append only if not a case-insensitive duplicate of an existing entry.
        if new_situation and not any(
            existing.lower() == new_situation.lower() for existing in situations
        ):
            situations.append(new_situation)
        update["learning_context_detail"] = {**detail, "situations": situations[:20]}

    update["pending_changes"] = [
        p for p in doc.get("pending_changes", []) if p.get("field") != field
    ]

    result = await profiles_col().find_one_and_update(
        {"user_id": user_id}, {"$set": update}, return_document=True
    )
    result.pop("_id", None)
    return result


@router.post("/pending-changes/{field}/dismiss", response_model=ProfileResponse)
async def dismiss_pending_change(field: str, user_id: str = Depends(require_auth)):
    """Discard a pending profile-agent proposal without applying it."""
    if field not in {f.value for f in ProposableField}:
        raise HTTPException(status_code=400, detail="Unknown field")

    doc = await profiles_col().find_one({"user_id": user_id}, {"pending_changes": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Profile not found")

    remaining = [p for p in doc.get("pending_changes", []) if p.get("field") != field]
    result = await profiles_col().find_one_and_update(
        {"user_id": user_id}, {"$set": {"pending_changes": remaining}}, return_document=True
    )
    result.pop("_id", None)
    return result


class MemoryEditRequest(BaseModel):
    """Request body for POST /api/profile/memory-edit."""

    message: str


@router.post("/memory-edit")
async def memory_edit(body: MemoryEditRequest, user_id: str = Depends(require_auth)) -> dict:
    """Apply a direct natural-language instruction to L1 memory (Settings > Memory
    chat box). Unlike pending-changes, this is user-authored — it applies
    immediately, no accept/dismiss step. See app/services/memory_editor.py.
    """
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    return await apply_memory_edit(user_id, message)
