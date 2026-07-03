"""Migration script: Convert existing sessions to topic threads.

Reads all documents from the `sessions` collection and creates corresponding
topic documents in the `topics` collection.

- Sessions with zero messages are skipped.
- Already-migrated sessions (matched via `migratedFrom` field) are skipped for idempotency.
- Titles are derived from session.title (if not "Untitled session") or from mode + topic.
- Message roles are normalized: "mentor" → "assistant".
- Token counts are estimated per message using the shared tiktoken-based counter.

Usage:
    python -m scripts.migrate_sessions_to_topics

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

import asyncio
import logging
import sys
from uuid import uuid4

from app.config.database import connect_db, disconnect_db, sessions_col, topics_col
from app.services.token_budget import count_tokens

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def derive_title(session: dict) -> str:
    """Derive a topic title from a session document.

    Uses the session's existing title if it's meaningful (not "Untitled session").
    Otherwise constructs from mode and topic fields.
    """
    title = session.get("title", "").strip()
    if title and title != "Untitled session":
        return title[:100]  # Enforce max length

    mode = session.get("mode", "topic")
    topic = session.get("topic")

    if topic:
        derived = f"{mode.capitalize()} Session - {topic}"
    else:
        derived = f"{mode.capitalize()} Session"

    return derived[:100]


def normalize_role(role: str) -> str:
    """Normalize message role: 'mentor' → 'assistant'."""
    if role == "mentor":
        return "assistant"
    return role


def estimate_token_count(content: str) -> int:
    """Estimate token count for message content using tiktoken."""
    return count_tokens(content or "")


def convert_message(msg: dict, fallback_timestamp: str | None = None) -> dict:
    """Convert a session message dict to the topic Message format.

    Args:
        msg: Original session message with role, content, and optional timestamp.
        fallback_timestamp: Timestamp to use if the message has no timestamp.

    Returns:
        A topic-format message dict.
    """
    content = msg.get("content", "")
    return {
        "type": "message",
        "id": str(uuid4()),
        "role": normalize_role(msg.get("role", "user")),
        "content": content,
        "timestamp": msg.get("timestamp") or fallback_timestamp,
        "tokenCount": estimate_token_count(content),
    }


def build_topic_document(session: dict) -> dict:
    """Build a topic document from a session document.

    Args:
        session: The original session document from MongoDB.

    Returns:
        A topic document ready for insertion into the topics collection.
    """
    messages = session.get("messages", [])
    session_created_at = session.get("created_at")

    converted_messages = [
        convert_message(msg, fallback_timestamp=session_created_at)
        for msg in messages
    ]

    # Determine timestamps
    last_message_timestamp = None
    if converted_messages:
        last_message_timestamp = converted_messages[-1].get("timestamp")

    first_message_timestamp = None
    if converted_messages:
        first_message_timestamp = converted_messages[0].get("timestamp")

    total_tokens = sum(msg["tokenCount"] for msg in converted_messages)

    return {
        "topicId": str(uuid4()),
        "userId": session.get("user_id", ""),
        "title": derive_title(session),
        "status": "active",
        "mode": session.get("mode"),
        "createdAt": session_created_at or first_message_timestamp,
        "lastActiveAt": last_message_timestamp or session_created_at,
        "messages": converted_messages,
        "compactionCount": 0,
        "metadata": {
            "totalMessageCount": len(converted_messages),
            "currentTokenEstimate": total_tokens,
        },
        "version": 0,
        "migratedFrom": session.get("session_id"),
    }


async def migrate_sessions() -> dict:
    """Run the migration: convert all sessions to topics.

    Returns:
        A summary dict with counts of migrated, skipped_empty, skipped_existing, and errors.
    """
    migrated = 0
    skipped_empty = 0
    skipped_existing = 0
    errors = 0

    sessions_collection = sessions_col()
    topics_collection = topics_col()

    cursor = sessions_collection.find({})
    sessions = await cursor.to_list(length=None)

    logger.info(f"Found {len(sessions)} sessions to process.")

    for session in sessions:
        session_id = session.get("session_id", "unknown")
        try:
            # Skip sessions with zero messages
            messages = session.get("messages", [])
            if not messages:
                skipped_empty += 1
                continue

            # Idempotency check: skip if already migrated
            existing = await topics_collection.find_one(
                {"migratedFrom": session_id}
            )
            if existing:
                skipped_existing += 1
                continue

            # Build and insert the topic document
            topic_doc = build_topic_document(session)
            await topics_collection.insert_one(topic_doc)
            migrated += 1

        except Exception as e:
            errors += 1
            logger.error(f"Error migrating session {session_id}: {e}")

    summary = {
        "migrated": migrated,
        "skipped_empty": skipped_empty,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }

    logger.info(
        f"Migration complete: Migrated {migrated} sessions, "
        f"skipped {skipped_empty} (empty), "
        f"skipped {skipped_existing} (already migrated), "
        f"{errors} errors."
    )

    return summary


async def main() -> None:
    """Entry point: connect to DB, run migration, disconnect."""
    logger.info("Starting session-to-topic migration...")
    await connect_db()
    try:
        await migrate_sessions()
    finally:
        await disconnect_db()
    logger.info("Migration finished.")


if __name__ == "__main__":
    asyncio.run(main())
