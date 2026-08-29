"""Skill graph repository: upserts skill nodes in MongoDB.

Provides the `apply_update` function that merges a validated
SessionSkillUpdate into the skill_graph collection. Failures are
logged but never raised — the skill graph write is non-blocking
to the session-end pipeline.
"""

import logging
from datetime import datetime, timezone

from app.config.database import skill_graph_col
from app.models.session import SessionSkillUpdate

logger = logging.getLogger(__name__)


async def apply_update(user_id: str, skill_update: SessionSkillUpdate) -> None:
    """Upsert a skill graph node with the latest session skill data.

    Uses MongoDB update_one with upsert=True on the compound index
    (user_id, topic). Writes current_level (the field planning reads), plus
    weak_areas, strong_areas, last_studied.

    On MongoDB write failure, logs the error and returns without raising.
    This keeps the session-end pipeline non-blocking.

    Args:
        user_id: The authenticated user's ID.
        skill_update: Validated skill update extracted from the session.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()

        # new_level vocab is graph-canonical (no translation).
        current_level = skill_update.new_level.value
        existing = await skill_graph_col().find_one(
            {"user_id": user_id, "topic": skill_update.topic},
            {"current_level": 1, "_id": 0},
        )
        # Remember the level we're replacing so the UI can show a "since last
        # session" delta (issue #16). None for a brand-new topic.
        previous_level = (existing or {}).get("current_level")

        await skill_graph_col().update_one(
            {"user_id": user_id, "topic": skill_update.topic},
            {
                "$set": {
                    "user_id": user_id,
                    "topic": skill_update.topic,
                    "current_level": current_level,
                    "previous_level": previous_level,
                    "weak_areas": skill_update.weak_areas,
                    "strong_areas": skill_update.strong_areas,
                    "last_studied": now,
                    # This is a verified write (diagnostic verdict, periodic
                    # checkpoint, or session-end) — no longer just the
                    # onboarding placeholder guess.
                    "assessed": True,
                }
            },
            upsert=True,
        )

        logger.info(
            "Skill graph upserted — user_id=%s, topic=%s, level=%s",
            user_id,
            skill_update.topic,
            current_level,
        )

    except Exception as e:
        logger.error(
            "Skill graph write failed — user_id=%s, topic=%s, error=%s",
            user_id,
            skill_update.topic,
            str(e),
        )
