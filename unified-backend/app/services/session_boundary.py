"""SessionBoundary — closes a topic's session when the topic window is
navigated away from / closed, on user logout, or when a single still-open
session has grown too large (HARD_CEILING_THRESHOLD) to wait for the
frontend to signal a close. See .kiro/specs/session-narrative-summary.

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
from app.services.session_compactor import close_session
from app.services.token_counter import TokenCounter

logger = logging.getLogger(__name__)

HARD_CEILING_THRESHOLD = 60
"""Usage percent (of the *uncovered* messages alone) at which a single
still-open session is force-closed early, without waiting for the frontend
to signal the window closed — the one case a purely window-close-triggered
compactor can't otherwise catch."""

_token_counter = TokenCounter()


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


async def maybe_force_close_long_session(topic_id: str, user_id: str, now: datetime) -> None:
    """Force-close the current still-open session early if its own
    not-yet-covered messages alone already exceed HARD_CEILING_THRESHOLD —
    covers the one case a purely window-close-triggered compactor can't: a
    single sitting long enough to blow the token budget before the frontend
    ever signals the window closed. Closing here doesn't end the literal
    chat session for the frontend's purposes; it just wraps up what's
    accumulated so far into its own narrative block and prunes it, same as
    any other close_session call."""
    topic = await topics_col().find_one(
        {"topicId": topic_id, "userId": user_id}, {"_id": 0, "messages": 1, "summaryBlocks": 1},
    )
    if not topic:
        return

    covered_ids = {mid for blk in topic.get("summaryBlocks") or [] for mid in blk.get("sourceSessionIds", [])}
    uncovered = [
        m for m in topic.get("messages", [])
        if m.get("type") == "message" and m.get("id") not in covered_ids
    ]
    if not uncovered:
        return

    if _token_counter.get_usage_percent(uncovered) > HARD_CEILING_THRESHOLD:
        await close_session(topic_id, user_id, upto_timestamp=now)


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
