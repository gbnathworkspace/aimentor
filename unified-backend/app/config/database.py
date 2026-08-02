"""Async MongoDB client and collection accessors."""

from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Connect to MongoDB and set up indexes."""
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.MONGODB_URI, tz_aware=True)
    _db = _client[settings.DATABASE_NAME]
    await _ensure_indexes()
    # Session persistence compound indexes (stale cleanup + timeout sweep)
    from app.core.indexes import ensure_indexes as ensure_session_indexes
    await ensure_session_indexes()
    # Auth collection indexes (users, refresh_tokens, otp_codes, oauth_states, rate_limits)
    from app.auth.indexes import ensure_auth_indexes
    await ensure_auth_indexes()
    # Topic and compaction_events collection indexes
    from app.topics.indexes import ensure_topic_indexes
    await ensure_topic_indexes()


async def disconnect_db() -> None:
    """Close the MongoDB connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the active database instance."""
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db


# Collection accessors
def profiles_col():
    return get_db()["profiles"]


def skill_graph_col():
    return get_db()["skill_graph"]


def sessions_col():
    return get_db()["sessions"]


def ingestion_jobs_col():
    return get_db()["ingestion_jobs"]


def embeddings_col():
    return get_db()["embeddings"]


def immediate_contexts_col():
    return get_db()["immediate_contexts"]


def topics_col():
    return get_db()["topics"]


def compaction_events_col():
    return get_db()["compaction_events"]


def subtopic_lists_col():
    return get_db()["subtopic_lists"]


def weight_nudges_col():
    return get_db()["weight_nudges"]


def document_upload_jobs_col():
    return get_db()["document_upload_jobs"]


@lru_cache
def get_s3_client():
    """Return a cached boto3 S3 client (region only).

    Credentials resolve via boto3's default provider chain: AWS_* env vars
    when set (local dev pointed at S3), otherwise the EC2 instance's IAM role
    in production. This app never stores static AWS keys.
    """
    import boto3

    settings = get_settings()
    return boto3.client("s3", region_name=settings.S3_REGION)


async def _ensure_indexes() -> None:
    """Create required indexes if they don't exist."""
    await profiles_col().create_index("user_id", unique=True)
    await skill_graph_col().create_index([("user_id", 1), ("topic", 1)], unique=True)
    await sessions_col().create_index("session_id", unique=True)
    await sessions_col().create_index("user_id")
    await ingestion_jobs_col().create_index("job_id", unique=True)
    await ingestion_jobs_col().create_index("user_id")
    await immediate_contexts_col().create_index("session_id")
    await subtopic_lists_col().create_index("topic", unique=True)
    await weight_nudges_col().create_index("user_id")
    # Document upload jobs: unique job_id, user_id lookup, and TTL on expires_at
    await document_upload_jobs_col().create_index("job_id", unique=True)
    await document_upload_jobs_col().create_index("user_id")
    await document_upload_jobs_col().create_index(
        "expires_at", expireAfterSeconds=0, name="idx_expires_at_ttl"
    )
