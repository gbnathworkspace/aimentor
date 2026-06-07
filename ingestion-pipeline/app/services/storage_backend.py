"""Storage backend abstraction for reading uploaded files.

Switch between local disk and S3 via STORAGE_BACKEND setting:
  STORAGE_BACKEND=local  — reads file bytes from the absolute path stored as the key
  STORAGE_BACKEND=s3     — downloads from S3 using the key as the S3 object key
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    @abstractmethod
    async def download(self, storage_key: str) -> bytes:
        """Return raw file bytes for the given storage key."""


class LocalBackend(StorageBackend):
    """Reads files from local disk. storage_key is the absolute path written by Next.js."""

    async def download(self, storage_key: str) -> bytes:
        logger.debug("Reading file from local disk: %s", storage_key)
        with open(storage_key, "rb") as f:
            return f.read()


class S3Backend(StorageBackend):
    """Downloads files from AWS S3. storage_key is the S3 object key."""

    async def download(self, storage_key: str) -> bytes:
        from app.config.database import get_s3_client

        settings = get_settings()
        if not settings.S3_BUCKET:
            raise RuntimeError("S3_BUCKET is not configured but STORAGE_BACKEND=s3")

        logger.debug("Downloading from S3: %s", storage_key)
        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=settings.S3_BUCKET, Key=storage_key)
        return response["Body"].read()


def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    if settings.STORAGE_BACKEND == "s3":
        return S3Backend()
    return LocalBackend()
