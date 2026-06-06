"""Environment-based configuration using pydantic BaseSettings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MongoDB
    MONGODB_URI: str
    DATABASE_NAME: str = "mentorman"

    # AWS S3
    S3_BUCKET: str
    S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str

    # Voyage AI embeddings
    VOYAGE_AI_API_KEY: str

    # LLM service (session summarization)
    LLM_ENDPOINT: str
    LLM_API_KEY: str


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
