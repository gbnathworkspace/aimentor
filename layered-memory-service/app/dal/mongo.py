import logging
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: MongoClient | None = None


def connect() -> None:
    global _client
    try:
        _client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            tlsAllowInvalidCertificates=True,
        )
        _client.admin.command("ping")
        _ensure_indexes()
        logger.info("MongoDB connected")
    except ConnectionFailure as e:
        logger.error("MongoDB connection failed: %s", e)
        raise


def disconnect() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("MongoDB disconnected")


def _db():
    if _client is None:
        raise RuntimeError("MongoDB not connected")
    return _client[settings.mongodb_db_name]


def get_profiles_collection() -> Collection:
    return _db()["profiles"]


def get_skill_graph_collection() -> Collection:
    return _db()["skill_graph"]


def get_sessions_collection() -> Collection:
    return _db()["sessions"]


def _ensure_indexes() -> None:
    db = _db()

    db["profiles"].create_index([("user_id", ASCENDING)], unique=True)

    db["skill_graph"].create_index(
        [("user_id", ASCENDING), ("topic", ASCENDING)], unique=True
    )

    db["sessions"].create_index([("user_id", ASCENDING)])
    db["sessions"].create_index([("session_id", ASCENDING)], unique=True)
