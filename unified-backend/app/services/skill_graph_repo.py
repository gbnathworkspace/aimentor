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
from app.services.onboarding_bootstrap import compute_gap

logger = logging.getLogger(__name__)


async def apply_update(user_id: str, skill_update: SessionSkillUpdate) -> None:
    """Upsert a skill graph node with the latest session skill data.

    Uses MongoDB update_one with upsert=True on the compound index
    (user_id, topic). Writes current_level (the field planning reads) and a
    recomputed string gap, plus weak_areas, strong_areas, last_studied.

    On MongoDB write failure, logs the error and returns without raising.
    This keeps the session-end pipeline non-blocking.

    Args:
        user_id: The authenticated user's ID.
        skill_update: Validated skill update extracted from the session.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()

        # gap was never recomputed on update (issue #3): write the level planning
        # actually reads (current_level) and derive gap from the existing
        # required_level. new_level vocab is now graph-canonical (no translation).
        current_level = skill_update.new_level.value
        existing = await skill_graph_col().find_one(
            {"user_id": user_id, "topic": skill_update.topic},
            {"required_level": 1, "current_level": 1, "_id": 0},
        )
        required_level = (existing or {}).get("required_level", "intermediate")
        # Remember the level we're replacing so the UI can show a "since last
        # session" delta (issue #16). None for a brand-new topic.
        previous_level = (existing or {}).get("current_level")
        gap = compute_gap(required_level, current_level)

        await skill_graph_col().update_one(
            {"user_id": user_id, "topic": skill_update.topic},
            {
                "$set": {
                    "user_id": user_id,
                    "topic": skill_update.topic,
                    "current_level": current_level,
                    "previous_level": previous_level,
                    "gap": gap,
                    "weak_areas": skill_update.weak_areas,
                    "strong_areas": skill_update.strong_areas,
                    "last_studied": now,
                }
            },
            upsert=True,
        )

        logger.info(
            "Skill graph upserted — user_id=%s, topic=%s, level=%s, gap=%s",
            user_id,
            skill_update.topic,
            current_level,
            gap,
        )

    except Exception as e:
        logger.error(
            "Skill graph write failed — user_id=%s, topic=%s, error=%s",
            user_id,
            skill_update.topic,
            str(e),
        )


def next_best_topics(nodes: list[dict], limit: int = 3) -> list[dict]:
    """Order skill nodes by prerequisite edges, then keep only unmastered ones
    in learn-next order (issue #10).

    Pure/sync, no DB access — takes the raw skill_graph list already fetched
    by context_assembler. A DFS post-order gives a valid topological order:
    every prerequisite is visited (and appended) before its dependent.

    # ponytail: no cycle guard beyond the visited set — edges are hand-seeded
    # linear chains, add real cycle detection if edges become user-editable.
    """
    topic_by_name = {n["topic"]: n for n in nodes}
    order: list[str] = []
    visited: set[str] = set()

    def visit(topic: str) -> None:
        if topic in visited or topic not in topic_by_name:
            return
        visited.add(topic)
        for prereq in topic_by_name[topic].get("prerequisites") or []:
            visit(prereq)
        order.append(topic)

    for n in nodes:
        visit(n["topic"])

    ranked = [
        {"topic": t, "gap": topic_by_name[t].get("gap", "unknown")}
        for t in order
        if topic_by_name[t].get("gap", "none") != "none"
    ]
    return ranked[:limit]
