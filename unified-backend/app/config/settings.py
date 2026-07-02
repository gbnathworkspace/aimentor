"""Unified configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB
    MONGODB_URI: str
    DATABASE_NAME: str = "mentorman"

    # Auth — Self-hosted JWT
    JWT_SECRET: str = "change-me-in-production"

    # Auth — OAuth providers
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/auth/oauth/callback"

    # Auth — Email delivery
    EMAIL_BACKEND: Literal["console", "api"] = "console"
    EMAIL_API_URL: Optional[str] = None
    EMAIL_API_KEY: Optional[str] = None
    EMAIL_FROM: str = "noreply@mentorman.app"

    # Auth — legacy service-to-service (kept behind a flag during transition)
    MENTORMAN_API_KEY: Optional[str] = None
    LEGACY_AUTH_ENABLED: bool = True

    # CORS — allowed browser origins (dev only; prod is same-origin)
    CORS_ORIGINS: str = "http://localhost:5173"

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

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS (comma-separated) into a list of origins."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Fails fast if required vars are missing."""
    return Settings()
