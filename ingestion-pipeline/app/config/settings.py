"""Environment-based configuration using pydantic BaseSettings."""

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MongoDB
    MONGODB_URI: str
    DATABASE_NAME: str = "mentorman"

    # Storage backend: 'local' (disk) or 's3' (AWS S3)
    STORAGE_BACKEND: Literal["local", "s3"] = "local"

    # AWS S3 (only required when STORAGE_BACKEND='s3')
    S3_BUCKET: Optional[str] = None
    S3_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Voyage AI embeddings
    VOYAGE_AI_API_KEY: str

    # LLM service (session summarization)
    LLM_ENDPOINT: str
    LLM_API_KEY: str


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
