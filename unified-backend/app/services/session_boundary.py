"""SessionBoundary — closes a topic's session when the topic window is
navigated away from / closed, or on user logout. See
.kiro/specs/session-narrative-summary.

Operates entirely on topics_col (topic.messages timestamps) — no dependency
on sessions_col / SessionManager (Requirement 6.1).

A session's end is driven by the frontend telling us the topic window is no
longer open (route change, tab/browser close via a keepalive request, or
component unmount) rather than by an inactivity timer — a topic left open
but idle does not close on its own.
"""

import logging
from datetime import datetime

from app.config.database import topics_col
from app.services.session_summarizer import close_session

logger = logging.getLogger(__name__)


async def close_session_for_topic(topic_id: str, user_id: str) -> None:
    """Close the session for one topic, using its own last-message
    timestamp as the close point. close_session no-ops if there are no
    messages since the last close (Requirement 1.5)."""
    topic = await topics_col().find_one(
        {"topicId": topic_id, "userId": user_id}, {"_id": 0, "messages": 1},
    )
    if not topic:
        return

    messages = [m for m in topic.get("messages", []) if m.get("type") == "message"]
    if not messages:
        return

    last_ts: datetime | None = messages[-1].get("timestamp")
    if not last_ts:
        return

    await close_session(topic_id, user_id, upto_timestamp=last_ts)


async def close_all_sessions_for_user(user_id: str) -> None:
    """Close every topic this user has an unclosed session in, using each
    topic's own last-message timestamp (Requirement 1.3, 6.2)."""
    cursor = topics_col().find(
        {"userId": user_id}, {"_id": 0, "topicId": 1, "messages": 1},
    )
    async for topic in cursor:
        messages = [m for m in topic.get("messages", []) if m.get("type") == "message"]
        if not messages:
            continue
        last_ts = messages[-1].get("timestamp")
        if not last_ts:
            continue
        await close_session(topic["topicId"], user_id, upto_timestamp=last_ts)
