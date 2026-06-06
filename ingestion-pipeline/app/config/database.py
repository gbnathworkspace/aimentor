"""MongoDB and S3 client initialization with connection helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.config.settings import get_settings


@lru_cache
def get_mongo_client() -> AsyncIOMotorClient:
    """Return a cached (singleton) async MongoDB client."""
    settings = get_settings()
    return AsyncIOMotorClient(settings.MONGODB_URI)


def get_database() -> AsyncIOMotorDatabase:
    """Return the application database using DATABASE_NAME from settings."""
    settings = get_settings()
    client = get_mongo_client()
    return client[settings.DATABASE_NAME]


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Return a typed collection reference by name."""
    return get_database()[name]


# --- Convenience collection accessors ---


def get_ingestion_jobs_collection() -> AsyncIOMotorCollection:
    """Return the ingestion_jobs collection."""
    return get_collection("ingestion_jobs")


def get_users_collection() -> AsyncIOMotorCollection:
    """Return the users collection (Core Profile)."""
    return get_collection("users")


def get_skill_graph_collection() -> AsyncIOMotorCollection:
    """Return the skill_graph collection."""
    return get_collection("skill_graph")


def get_sessions_collection() -> AsyncIOMotorCollection:
    """Return the sessions collection."""
    return get_collection("sessions")


def get_embeddings_collection() -> AsyncIOMotorCollection:
    """Return the embeddings collection (Atlas Vector Search)."""
    return get_collection("embeddings")


# --- S3 client ---


@lru_cache
def get_s3_client() -> Any:
    """Return a cached boto3 S3 client configured from settings.

    Returns a boto3 S3 client instance (botocore.client.S3).
    """
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
