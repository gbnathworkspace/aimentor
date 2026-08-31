"""One-off script: print the most recently active topic ("session") and its
last few messages. Run from unified-backend/ with MONGODB_URI set:

    python scripts/get_latest_session.py [--legacy] [--messages N]

--legacy pulls from the old sessions_col instead of topics_col (see
README's Agentic RAG section / session_boundary.py — sessions_col is the
dead pipeline nothing in the live chat UI writes to anymore).
"""

import argparse
import asyncio
import json
from datetime import datetime

from app.config.database import connect_db, disconnect_db, sessions_col, topics_col


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def get_latest_topic(message_count: int) -> dict | None:
    topic = await topics_col().find_one(
        {}, sort=[("lastActiveAt", -1)],
    )
    if topic is None:
        return None
    topic.pop("_id", None)
    messages = [m for m in topic.get("messages", []) if m.get("type") == "message"]
    topic["messages"] = messages[-message_count:]
    return topic


async def get_latest_session(message_count: int) -> dict | None:
    session = await sessions_col().find_one(
        {}, sort=[("updated_at", -1)],
    )
    if session is None:
        return None
    session.pop("_id", None)
    session["messages"] = session.get("messages", [])[-message_count:]
    return session


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--legacy", action="store_true",
        help="Query sessions_col instead of topics_col",
    )
    parser.add_argument(
        "--messages", type=int, default=6,
        help="Number of most recent messages to include (default 6)",
    )
    args = parser.parse_args()

    await connect_db()
    try:
        doc = (
            await get_latest_session(args.messages)
            if args.legacy
            else await get_latest_topic(args.messages)
        )
        if doc is None:
            print("No documents found.")
            return
        print(json.dumps(doc, indent=2, default=_json_default))
    finally:
        await disconnect_db()


if __name__ == "__main__":
    asyncio.run(main())
