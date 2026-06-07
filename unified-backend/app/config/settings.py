"""Unified configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB
    MONGODB_URI: str
    DATABASE_NAME: str = "mentorman"

    # Auth — Clerk (primary: networkless JWKS verification of session JWTs)
    CLERK_ISSUER: Optional[str] = None  # e.g. https://your-app.clerk.accounts.dev
    CLERK_JWKS_URL: Optional[str] = None  # defaults to {issuer}/.well-known/jwks.json

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
    def clerk_jwks_url(self) -> Optional[str]:
        """Resolve the JWKS URL, deriving it from the issuer if not set explicitly."""
        if self.CLERK_JWKS_URL:
            return self.CLERK_JWKS_URL
        if self.CLERK_ISSUER:
            return f"{self.CLERK_ISSUER.rstrip('/')}/.well-known/jwks.json"
        return None

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS (comma-separated) into a list of origins."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Fails fast if required vars are missing."""
    return Settings()
