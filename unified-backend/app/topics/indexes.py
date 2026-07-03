"""MongoDB index definitions for the topics and compaction_events collections.

Ensures compound indexes required by the topic conversations and compaction
pipeline are created on application startup.
"""

from pymongo import ASCENDING, DESCENDING

from app.config.database import topics_col, compaction_events_col


async def ensure_topic_indexes() -> None:
    """Create indexes for topics and compaction_events collections.

    Indexes:
      topics:
        - topicId (unique) — fast lookup by topic identifier
        - { userId: 1, status: 1, lastActiveAt: -1 } — sidebar listing query
          (active topics for a user, ordered by most recent activity)

      compaction_events:
        - eventId (unique) — fast lookup by event identifier
        - { topicId: 1, timestamp: -1 } — compaction history query per topic
    """
    # --- topics collection ---
    topics = topics_col()

    await topics.create_index(
        "topicId",
        unique=True,
        name="idx_topics_topicId",
    )

    await topics.create_index(
        [("userId", ASCENDING), ("status", ASCENDING), ("lastActiveAt", DESCENDING)],
        name="idx_topics_userId_status_lastActiveAt",
    )

    # --- compaction_events collection ---
    compaction_events = compaction_events_col()

    await compaction_events.create_index(
        "eventId",
        unique=True,
        name="idx_compaction_events_eventId",
    )

    await compaction_events.create_index(
        [("topicId", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_compaction_events_topicId_timestamp",
    )
