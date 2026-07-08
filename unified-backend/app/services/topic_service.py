"""TopicService — CRUD and lifecycle management for topic threads.

Handles topic creation, retrieval, listing, renaming, and archival.
Enforces title validation, ownership checks, and status transitions.
Also handles message append with optimistic concurrency and pagination.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config.database import topics_col
from app.services.token_counter import TokenCounter


MAX_MESSAGE_LENGTH = 50_000
"""Maximum allowed message content length in characters."""

MAX_RETRIES = 3
"""Maximum optimistic concurrency retries before aborting."""


class TopicService:
    """Manages topic thread CRUD operations and lifecycle transitions."""

    def __init__(self):
        self._token_counter = TokenCounter()

    # --- Creation ---

    async def create_topic(self, user_id: str, title: str) -> dict:
        """Create a new topic with validated title.

        Args:
            user_id: The authenticated user's ID.
            title: The topic title (1-100 chars after trim).

        Returns:
            The newly created topic document.

        Raises:
            HTTPException: 400 if title is invalid.
        """
        validated_title = self._validate_title(title)

        now = datetime.now(timezone.utc)
        topic_id = str(uuid.uuid4())

        doc = {
            "topicId": topic_id,
            "userId": user_id,
            "title": validated_title,
            "status": "active",
            "mode": None,
            "createdAt": now,
            "lastActiveAt": now,
            "messages": [],
            "compactionCount": 0,
            "metadata": {
                "totalMessageCount": 0,
                "currentTokenEstimate": 0,
            },
            "version": 0,
        }

        await topics_col().insert_one(doc)
        # Remove MongoDB internal _id before returning
        doc.pop("_id", None)
        return doc

    # --- Retrieval ---

    async def get_topic(self, topic_id: str, user_id: str) -> dict:
        """Get a topic by ID with ownership check.

        Returns the same 404 for both not-found and unauthorized access
        to prevent topic ID enumeration (Req 15.5).

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.

        Returns:
            The topic document.

        Raises:
            HTTPException: 404 if topic not found or user doesn't own it.
        """
        topic = await topics_col().find_one(
            {"topicId": topic_id, "userId": user_id},
            {"_id": 0},
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        return topic

    # --- Listing ---

    async def list_topics(self, user_id: str) -> list[dict]:
        """List active topics for user, ordered by lastActiveAt desc, max 50.

        Uses projection for fast sidebar loading (Req 14.2). Includes a
        message preview from the last message in the thread.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            List of TopicListItem dicts with topicId, title, status,
            lastActiveAt, mode, and messagePreview.
        """
        cursor = topics_col().find(
            {"userId": user_id, "status": "active"},
            {
                "_id": 0,
                "topicId": 1,
                "title": 1,
                "status": 1,
                "lastActiveAt": 1,
                "mode": 1,
                "messages": {"$slice": -1},  # last message only for preview
            },
        ).sort("lastActiveAt", -1).limit(50)

        topics = await cursor.to_list(length=50)

        # Post-process: extract message preview from last message
        for topic in topics:
            messages = topic.pop("messages", [])
            if messages:
                last_msg = messages[-1]
                content = last_msg.get("content", "")
                topic["messagePreview"] = content[:80]
            else:
                topic["messagePreview"] = ""

        return topics

    async def list_archived_topics(self, user_id: str) -> list[dict]:
        """List archived topics for viewing (Req 3.4).

        Args:
            user_id: The authenticated user's ID.

        Returns:
            List of archived TopicListItem dicts ordered by lastActiveAt desc.
        """
        cursor = topics_col().find(
            {"userId": user_id, "status": "archived"},
            {
                "_id": 0,
                "topicId": 1,
                "title": 1,
                "status": 1,
                "lastActiveAt": 1,
                "mode": 1,
                "messages": {"$slice": -1},
            },
        ).sort("lastActiveAt", -1).limit(50)

        topics = await cursor.to_list(length=50)

        for topic in topics:
            messages = topic.pop("messages", [])
            if messages:
                last_msg = messages[-1]
                content = last_msg.get("content", "")
                topic["messagePreview"] = content[:80]
            else:
                topic["messagePreview"] = ""

        return topics

    # --- Archival ---

    async def archive_topic(self, topic_id: str, user_id: str) -> None:
        """Archive a topic. Only active → archived transition is allowed.

        Preserves all topic data (messages, summary blocks, compaction events).

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.

        Raises:
            HTTPException: 404 if topic not found or user doesn't own it.
            HTTPException: 409 if the topic is not in "active" status.
        """
        topic = await topics_col().find_one(
            {"topicId": topic_id, "userId": user_id}
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        if topic["status"] != "active":
            raise HTTPException(
                status_code=409,
                detail="Only active topics can be archived",
            )

        await topics_col().update_one(
            {"topicId": topic_id, "userId": user_id},
            {"$set": {"status": "archived"}},
        )

    # --- Rename ---

    async def rename_topic(self, topic_id: str, user_id: str, new_title: str) -> dict:
        """Rename a topic. Validates the new title.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            new_title: The new title string.

        Returns:
            The updated topic document.

        Raises:
            HTTPException: 400 if new_title is invalid.
            HTTPException: 404 if topic not found or user doesn't own it.
        """
        validated_title = self._validate_title(new_title)

        result = await topics_col().find_one_and_update(
            {"topicId": topic_id, "userId": user_id},
            {"$set": {"title": validated_title}},
            return_document=True,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Topic not found")

        result.pop("_id", None)
        return result

    # --- Validation helpers ---

    @staticmethod
    def _validate_title(title: str) -> str:
        """Validate and return trimmed title.

        Args:
            title: Raw title string.

        Returns:
            Trimmed title.

        Raises:
            HTTPException: 400 if title is empty after trim or exceeds 100 chars.
        """
        trimmed = title.strip()
        if not trimmed or len(trimmed) > 100:
            raise HTTPException(
                status_code=400,
                detail="Title must be between 1 and 100 non-whitespace-only characters",
            )
        return trimmed

    # --- Message Operations ---

    async def append_message(self, topic_id: str, user_id: str, message: dict) -> dict:
        """Append a message to a topic's messages array.

        Validates content length, topic status, and chronological ordering.
        Estimates token count using TokenCounter.count_message().
        Updates lastActiveAt and currentTokenEstimate atomically.
        Uses optimistic concurrency (version field) with up to 3 retries.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            message: A dict with keys: type, id, role, content, timestamp.

        Returns:
            The appended message dict with tokenCount populated.

        Raises:
            HTTPException: 400 if content exceeds 50,000 chars.
            HTTPException: 409 if topic status is not "active" or concurrent conflict.
            HTTPException: 404 if topic not found or user doesn't own it.
        """
        # Validate content length
        content = message.get("content", "")
        if len(content) > MAX_MESSAGE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Message content must not exceed {MAX_MESSAGE_LENGTH} characters",
            )

        # Estimate token count for the message
        token_count = self._token_counter.count_message(message)
        message["tokenCount"] = token_count

        appended_message = None

        def update_fn(topic: dict) -> dict:
            nonlocal appended_message

            # Reject if topic is not active
            if topic.get("status") != "active":
                raise HTTPException(
                    status_code=409,
                    detail="Topic is not active and cannot accept messages",
                )

            # Enforce chronological ordering
            messages = topic.get("messages", [])
            if messages:
                last_msg = messages[-1]
                last_ts = last_msg.get("timestamp")
                msg_ts = message.get("timestamp")
                if last_ts and msg_ts and msg_ts < last_ts:
                    raise HTTPException(
                        status_code=400,
                        detail="Message timestamp must be >= last message timestamp (chronological order)",
                    )

            # Calculate new token estimate
            current_estimate = topic.get("metadata", {}).get("currentTokenEstimate", 0)
            new_estimate = current_estimate + token_count

            now = datetime.now(timezone.utc)
            appended_message = message

            return {
                "push_message": message,
                "lastActiveAt": now,
                "metadata.currentTokenEstimate": new_estimate,
                "metadata.totalMessageCount": topic.get("metadata", {}).get("totalMessageCount", 0) + 1,
            }

        await self._optimistic_append(topic_id, user_id, update_fn)
        return appended_message

    async def get_messages(
        self, topic_id: str, user_id: str, limit: int = 50, before: str | None = None
    ) -> list[dict]:
        """Get messages from a topic with pagination.

        Returns messages ordered by timestamp ascending.
        If 'before' is provided, return messages with timestamp < before.
        Ownership check via userId filter.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            limit: Maximum number of messages to return (default 50).
            before: ISO timestamp string; return messages before this time.

        Returns:
            List of message dicts ordered by timestamp ascending.

        Raises:
            HTTPException: 404 if topic not found or user doesn't own it.
        """
        topic = await topics_col().find_one(
            {"topicId": topic_id, "userId": user_id},
            {"_id": 0, "messages": 1},
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        messages = topic.get("messages", [])

        # Filter by 'before' timestamp if provided
        if before is not None:
            if isinstance(before, str):
                before_dt = datetime.fromisoformat(before)
            else:
                before_dt = before
            messages = [m for m in messages if m.get("timestamp") < before_dt]

        # Messages are stored in chronological order; return last `limit` items
        # to get the most recent messages (still in ascending order)
        if len(messages) > limit:
            messages = messages[-limit:]

        return messages

    async def get_messages_paginated(
        self, topic_id: str, user_id: str, limit: int = 50, skip: int = 0
    ) -> dict:
        """Get messages with pagination for large topics (Req 14.4).

        For topics with >500 messages, returns only a page of messages.
        Older messages (including summary blocks) can be loaded on demand
        via scroll by increasing the skip parameter.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            limit: Maximum number of messages to return (default 50, max 100).
            skip: Number of messages to skip from the end (for scrolling back).

        Returns:
            Dict with:
              - "messages": list of message dicts (ascending order)
              - "total": total number of messages in topic
              - "hasMore": bool indicating if there are older messages

        Raises:
            HTTPException: 404 if topic not found or user doesn't own it.
        """
        topic = await topics_col().find_one(
            {"topicId": topic_id, "userId": user_id},
            {"_id": 0, "messages": 1},
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        all_messages = topic.get("messages", [])
        total = len(all_messages)

        # Clamp limit to valid range
        limit = max(1, min(limit, 100))

        # Calculate the slice from the end (most recent first for pagination)
        # skip=0 means get the most recent `limit` messages
        # skip=50 means skip the 50 most recent and get the next `limit`
        end_index = total - skip
        start_index = max(0, end_index - limit)

        if end_index <= 0:
            return {"messages": [], "total": total, "hasMore": False}

        end_index = max(0, end_index)
        page = all_messages[start_index:end_index]
        has_more = start_index > 0

        return {"messages": page, "total": total, "hasMore": has_more}

    # --- Optimistic Concurrency Helper ---

    async def _optimistic_append(self, topic_id: str, user_id: str, update_fn) -> None:
        """Execute a write with optimistic concurrency control.

        Reads the topic, applies update_fn to produce the update fields,
        then attempts a conditional write using the version field.
        Retries up to MAX_RETRIES times on conflict.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            update_fn: A callable that receives the topic dict and returns
                       a dict of fields to set. May include a special key
                       "push_message" to push a message to the messages array.

        Raises:
            HTTPException: 404 if topic not found.
            HTTPException: 409 if conflict persists after MAX_RETRIES attempts.
        """
        for attempt in range(MAX_RETRIES):
            topic = await topics_col().find_one(
                {"topicId": topic_id, "userId": user_id}
            )
            if not topic:
                raise HTTPException(status_code=404, detail="Topic not found")

            current_version = topic.get("version", 0)

            # Apply the update function (may raise HTTPException for validation)
            update = update_fn(topic)

            # Separate the push operation from $set fields
            push_message = update.pop("push_message", None)

            # Build the MongoDB update operation
            set_fields = {**update, "version": current_version + 1}
            mongo_update: dict = {"$set": set_fields}

            if push_message is not None:
                mongo_update["$push"] = {"messages": push_message}

            result = await topics_col().update_one(
                {"topicId": topic_id, "userId": user_id, "version": current_version},
                mongo_update,
            )

            if result.modified_count == 1:
                return  # success

        raise HTTPException(
            status_code=409,
            detail="Conflict: concurrent modification detected after maximum retries",
        )
