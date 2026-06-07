"""Unit tests for app/config/settings.py — fail-fast validation."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


class TestSettingsValidation:
    """Verify Settings class fails fast on missing required env vars."""

    def _make_env(self, overrides: dict | None = None) -> dict:
        """Return a minimal valid env dict."""
        base = {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MENTORMAN_API_KEY": "test-key",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "VOYAGE_API_KEY": "voy-test",
        }
        if overrides:
            base.update(overrides)
        return base

    def test_valid_settings_with_all_required(self):
        """Settings instantiates when all required vars are present."""
        from app.config.settings import Settings

        env = self._make_env()
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)

        assert s.MONGODB_URI == "mongodb://localhost:27017"
        assert s.DATABASE_NAME == "mentorman"
        assert s.PORT == 8000
        assert s.LOG_LEVEL == "INFO"
        assert s.STORAGE_BACKEND == "local"
        assert s.S3_REGION == "ap-south-1"

    def test_missing_mongodb_uri_raises(self):
        """Settings raises ValidationError if MONGODB_URI is missing."""
        from app.config.settings import Settings

        env = self._make_env()
        del env["MONGODB_URI"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_missing_mentorman_api_key_raises(self):
        """Settings raises ValidationError if MENTORMAN_API_KEY is missing."""
        from app.config.settings import Settings

        env = self._make_env()
        del env["MENTORMAN_API_KEY"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_missing_anthropic_api_key_raises(self):
        """Settings raises ValidationError if ANTHROPIC_API_KEY is missing."""
        from app.config.settings import Settings

        env = self._make_env()
        del env["ANTHROPIC_API_KEY"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_missing_voyage_api_key_raises(self):
        """Settings raises ValidationError if VOYAGE_API_KEY is missing."""
        from app.config.settings import Settings

        env = self._make_env()
        del env["VOYAGE_API_KEY"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_storage_backend_literal_validation(self):
        """Settings rejects invalid STORAGE_BACKEND values."""
        from app.config.settings import Settings

        env = self._make_env({"STORAGE_BACKEND": "gcs"})
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError):
                Settings(_env_file=None)

    def test_storage_backend_s3_accepted(self):
        """Settings accepts 's3' as STORAGE_BACKEND."""
        from app.config.settings import Settings

        env = self._make_env({"STORAGE_BACKEND": "s3", "S3_BUCKET_NAME": "my-bucket"})
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
        assert s.STORAGE_BACKEND == "s3"
        assert s.S3_BUCKET_NAME == "my-bucket"

    def test_port_accepts_string_int(self):
        """Settings coerces PORT from string to int."""
        from app.config.settings import Settings

        env = self._make_env({"PORT": "9000"})
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
        assert s.PORT == 9000

    def test_extra_env_vars_ignored(self):
        """Settings ignores unknown environment variables (extra='ignore')."""
        from app.config.settings import Settings

        env = self._make_env({"UNKNOWN_VAR": "should-be-ignored"})
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
        assert not hasattr(s, "UNKNOWN_VAR")


class TestGetSettings:
    """Verify get_settings() caching behavior."""

    def test_get_settings_returns_settings_instance(self):
        """get_settings() returns a Settings instance."""
        from app.config.settings import Settings, get_settings

        env = {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MENTORMAN_API_KEY": "test-key",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "VOYAGE_API_KEY": "voy-test",
        }
        # Clear lru_cache before test
        get_settings.cache_clear()
        with patch.dict(os.environ, env, clear=True):
            s = get_settings()
        assert isinstance(s, Settings)
        # Clean up
        get_settings.cache_clear()
