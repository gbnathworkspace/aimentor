"""Overrides tests/conftest.py's fake-credentials fixture for this directory.

The parent conftest.py's autouse `setup_test_env` patches os.environ with a
fake ANTHROPIC_API_KEY ("sk-ant-test") for every test, so unit tests never
touch the real API. Evals are the one exception — they need the real key
from unified-backend/.env to make live calls. Redefining the same-named
fixture here shadows the parent's for everything under tests/evals/.
"""

import pytest

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def setup_test_env():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
