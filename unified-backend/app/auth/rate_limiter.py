"""Sliding-window rate limiter using MongoDB for attempt tracking."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.config.database import get_db


class RateLimiter:
    """Rate limiter using a sliding window strategy.

    Stores each attempt as an individual document in the rate_limits collection.
    Documents have an expires_at field used by a TTL index for automatic cleanup.

    Default: 5 attempts per 15-minute window per key+action pair.
    """

    def __init__(self, max_attempts: int = 5, window_minutes: int = 15):
        self.max_attempts = max_attempts
        self.window = timedelta(minutes=window_minutes)

    async def check_and_increment(self, key: str, action: str) -> None:
        """Check if rate limit exceeded for key+action. Increment counter.

        Raises HTTP 429 if limit exceeded.
        """
        db = get_db()
        now = datetime.now(timezone.utc)
        window_start = now - self.window

        # Count attempts in current window
        count = await db["rate_limits"].count_documents({
            "key": key,
            "action": action,
            "timestamp": {"$gte": window_start},
        })

        if count >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Try again in {self.window.seconds // 60} minutes.",
            )

        # Record this attempt
        await db["rate_limits"].insert_one({
            "key": key,
            "action": action,
            "timestamp": now,
            "expires_at": now + self.window,  # TTL index auto-deletes
        })

    async def reset(self, key: str, action: str) -> None:
        """Reset rate limit counter on successful action (e.g., successful login)."""
        db = get_db()
        await db["rate_limits"].delete_many({"key": key, "action": action})
