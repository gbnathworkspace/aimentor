"""Unified configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB
    MONGODB_URI: str
    DATABASE_NAME: str = "mentorman"

    # Auth
    MENTORMAN_API_KEY: str

    # LLM
    ANTHROPIC_API_KEY: str

    # Embeddings
    VOYAGE_API_KEY: str

    # Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Server
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Fails fast if required vars are missing."""
    return Settings()
