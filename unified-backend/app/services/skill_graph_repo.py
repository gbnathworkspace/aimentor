"""Skill graph repository: upserts skill nodes in MongoDB.

Provides the `apply_update` function that merges a list of per-subtopic
mastery updates into the skill_graph collection. Failures are logged but
never raised — the skill graph write is non-blocking to whatever pipeline
called it (diagnostic verdict, compaction extraction).
"""

import logging
from datetime import datetime, timezone

from app.config.database import skill_graph_col
from app.models.skill import SubtopicMasteryUpdate

logger = logging.getLogger(__name__)


async def apply_update(
    user_id: str, topic: str, subtopic_updates: list[SubtopicMasteryUpdate]
) -> None:
    """Merge per-subtopic mastery values into a skill graph node.

    Only the subtopics present in `subtopic_updates` are overwritten —
    every other key already in the node's `subtopic_mastery` map is left
    untouched (incremental update, not a replacement).

    On MongoDB write failure, logs the error and returns without raising.

    Args:
        user_id: The authenticated user's ID.
        topic: The topic this update applies to.
        subtopic_updates: Validated (subtopic, mastery) pairs to merge.
            Caller is responsible for validating subtopic names against
            the topic's canonical subtopic list first (see
            subtopic_weights.get_subtopics).
    """
    if not subtopic_updates:
        return

    try:
        now = datetime.now(timezone.utc).isoformat()

        set_fields = {
            f"subtopic_mastery.{u.subtopic}": u.mastery for u in subtopic_updates
        }
        set_fields.update({
            f"subtopic_last_studied.{u.subtopic}": now for u in subtopic_updates
        })
        set_fields.update({
            "user_id": user_id,
            "topic": topic,
            "last_studied": now,
        })

        await skill_graph_col().update_one(
            {"user_id": user_id, "topic": topic},
            {"$set": set_fields},
            upsert=True,
        )

        logger.info(
            "Skill graph upserted — user_id=%s, topic=%s, subtopics=%s",
            user_id,
            topic,
            [u.subtopic for u in subtopic_updates],
        )

    except Exception as e:
        logger.error(
            "Skill graph write failed — user_id=%s, topic=%s, error=%s",
            user_id,
            topic,
            str(e),
        )
