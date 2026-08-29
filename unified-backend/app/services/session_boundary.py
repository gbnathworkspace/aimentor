"""SessionBoundary — detects when a topic's session should close: a
10-minute inactivity gap, an idle sweep catching a gap with no next message,
or a user logout. See .kiro/specs/session-narrative-summary.

Operates entirely on topics_col (topic.messages timestamps) — no dependency
on sessions_col / SessionManager (Requirement 6.1).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config.database import topics_col
from app.services.session_summarizer import close_session

logger = logging.getLogger(__name__)

SESSION_IDLE_GAP_MINUTES = 10
IDLE_SWEEP_INTERVAL_SECONDS = 5 * 60


async def check_and_close_on_new_message(
    topic_id: str, user_id: str, new_message_ts: datetime
) -> None:
    """Compare new_message_ts to the topic's last message timestamp; if the
    gap exceeds SESSION_IDLE_GAP_MINUTES, close the session up to that last
    message (Requirement 1.1, 1.4 — role-agnostic gap)."""
    topic = await topics_col().find_one(
        {"topicId": topic_id, "userId": user_id}, {"_id": 0, "messages": 1},
    )
    if not topic:
        return

    messages = [m for m in topic.get("messages", []) if m.get("type") == "message"]
    if not messages:
        return

    last_ts = messages[-1].get("timestamp")
    if not last_ts:
        return

    gap = new_message_ts - last_ts
    if gap > timedelta(minutes=SESSION_IDLE_GAP_MINUTES):
        await close_session(topic_id, user_id, upto_timestamp=last_ts)


async def idle_sweep() -> int:
    """Find topics whose most recent message is more than
    SESSION_IDLE_GAP_MINUTES old and close them. close_session no-ops on
    topics already closed through their last message, so re-sweeping a
    long-idle topic is cheap but harmless (Requirement 1.2)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_IDLE_GAP_MINUTES)
    cursor = topics_col().find(
        {"lastActiveAt": {"$lt": cutoff}}, {"_id": 0, "topicId": 1, "userId": 1, "messages": 1},
    )
    closed = 0
    async for topic in cursor:
        messages = [m for m in topic.get("messages", []) if m.get("type") == "message"]
        if not messages:
            continue
        last_ts = messages[-1].get("timestamp")
        if not last_ts:
            continue
        await close_session(topic["topicId"], topic["userId"], upto_timestamp=last_ts)
        closed += 1
    return closed


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


async def periodic_sweep_loop() -> None:
    """Background loop, started at app boot — runs idle_sweep every
    IDLE_SWEEP_INTERVAL_SECONDS. No dedicated job-queue infra, consistent
    with this app's single-process deployment."""
    while True:
        try:
            closed = await idle_sweep()
            if closed:
                logger.info("Idle sweep: closed %d session(s)", closed)
        except Exception:
            logger.exception("Error during session idle sweep")
        await asyncio.sleep(IDLE_SWEEP_INTERVAL_SECONDS)
