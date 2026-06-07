"""Async MongoDB client and collection accessors."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Connect to MongoDB and set up indexes."""
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _db = _client[settings.DATABASE_NAME]
    await _ensure_indexes()


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


async def _ensure_indexes() -> None:
    """Create required indexes if they don't exist."""
    await profiles_col().create_index("user_id", unique=True)
    await skill_graph_col().create_index([("user_id", 1), ("topic", 1)], unique=True)
    await sessions_col().create_index("session_id", unique=True)
    await sessions_col().create_index("user_id")
    await ingestion_jobs_col().create_index("job_id", unique=True)
    await ingestion_jobs_col().create_index("user_id")
    await immediate_contexts_col().create_index("session_id")
