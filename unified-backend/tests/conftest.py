"""Shared test fixtures for the unified backend test suite."""

import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def setup_test_env():
    """Set up test environment variables for all tests."""
    get_settings.cache_clear()
    env = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "DATABASE_NAME": "mentorman_test",
        "MENTORMAN_API_KEY": "test-api-key",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "VOYAGE_API_KEY": "voy-test",
    }
    with patch.dict(os.environ, env, clear=True):
        get_settings()
        yield
    get_settings.cache_clear()


@pytest.fixture
def auth_headers():
    """Standard auth headers for test requests."""
    return {"X-User-Id": "test-user-123", "X-Api-Key": "test-api-key"}


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing the FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
