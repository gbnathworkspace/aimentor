"""Post-session L1 profiling agent.

Reads the same LLM response session_save_handler.py already gets at session-end
(a third key, "profile_signals", alongside narrative_summary/skill_update) and
turns it into PendingProfileChange entries. Never writes directly to the live
profile — see design_decisions/10_onboarding.md and issue #49: style_notes are
inferred, not self-reported, so every proposal sits in
profiles_col.pending_changes until the user accepts or dismisses it via
POST /api/profile/pending-changes/{field}/(accept|dismiss).

Only one live proposal per field: a new proposal for a field that already has
an unreviewed pending entry replaces it, so the user never sees a pile-up of
stale guesses about the same thing.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.config.database import profiles_col
from app.models.profile import PendingProfileChange, ProposableField, StyleNoteCategory

logger = logging.getLogger(__name__)

_VALID_FIELDS = {f.value for f in ProposableField}
_VALID_CATEGORIES = {c.value for c in StyleNoteCategory}


def _validate_signal(raw: Any, session_id: str) -> Optional[PendingProfileChange]:
    """Validate one LLM-proposed signal. Returns None if malformed or unrecognized —
    a bad proposal is silently dropped, not surfaced as an error (this is a
    best-effort enrichment step, not a required part of session-end)."""
    if not isinstance(raw, dict):
        return None

    field = raw.get("field")
    proposed_value = raw.get("proposed_value")
    reason = raw.get("reason")
    if field not in _VALID_FIELDS or not isinstance(proposed_value, dict) or not reason:
        return None

    if field == ProposableField.STYLE_NOTE.value:
        if proposed_value.get("category") not in _VALID_CATEGORIES or not proposed_value.get("note"):
            return None

    try:
        return PendingProfileChange(
            field=field,
            proposed_value=proposed_value,
            reason=str(reason)[:200],
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
        )
    except Exception:
        return None


async def propose_changes(user_id: str, session_id: str, raw_signals: list) -> None:
    """Validate and store proposed L1 changes from one session's transcript.

    Replaces any existing pending proposal for the same field. Never raises —
    logs and returns on failure, matching the rest of the session-end pipeline's
    fire-and-forget error handling (this must never block session-end).
    """
    if not raw_signals:
        return

    try:
        validated = [
            change for raw in raw_signals
            if (change := _validate_signal(raw, session_id)) is not None
        ]
        if not validated:
            return

        profile = await profiles_col().find_one({"user_id": user_id}, {"pending_changes": 1})
        existing = (profile or {}).get("pending_changes") or []
        proposed_fields = {c.field.value for c in validated}
        kept = [p for p in existing if p.get("field") not in proposed_fields]
        new_pending = kept + [c.model_dump(mode="json") for c in validated]

        await profiles_col().update_one(
            {"user_id": user_id},
            {"$set": {"pending_changes": new_pending}},
        )
        logger.info(
            "Proposed %d profile change(s) for user_id=%s from session_id=%s",
            len(validated), user_id, session_id,
        )
    except Exception as e:
        logger.warning(
            "Failed to propose profile changes — user_id=%s, session_id=%s, error=%s",
            user_id, session_id, str(e),
        )
