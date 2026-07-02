"""Property test — auth enforcement (spec Property 1).

For arbitrary header combinations, require_auth must reject (401) unless the
request carries a valid credential. Validates Requirements 5.1, 5.2, 5.4.
"""

import asyncio
import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _env():
    get_settings.cache_clear()
    env = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "MENTORMAN_API_KEY": "the-correct-key",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "VOYAGE_API_KEY": "voy-test",
        "LEGACY_AUTH_ENABLED": "true",
    }
    with patch.dict(os.environ, env, clear=True):
        get_settings()
        yield
    get_settings.cache_clear()


# Random api keys that are never the correct one.
_wrong_keys = st.text(min_size=0, max_size=20).filter(lambda s: s != "the-correct-key")
# Authorization values that are not a well-formed bearer token we accept.
_bad_auth = st.one_of(
    st.none(),
    st.text(max_size=20).filter(lambda s: not s.lower().startswith("bearer ")),
)


@settings(max_examples=150)
@given(authorization=_bad_auth, user_id=st.one_of(st.none(), st.text(max_size=20)), api_key=_wrong_keys)
def test_invalid_credentials_always_401(authorization, user_id, api_key):
    """No valid bearer + wrong/blank api key ⇒ always 401, never a silent pass."""
    from app.core.security import require_auth

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            require_auth(authorization=authorization, x_user_id=user_id, x_api_key=api_key)
        )
    assert exc.value.status_code == 401


@settings(max_examples=100)
@given(user_id=st.text(min_size=1, max_size=40))
def test_valid_legacy_key_returns_user_id(user_id):
    """Correct legacy key + any non-empty user id ⇒ that user id is returned."""
    from app.core.security import require_auth

    result = asyncio.run(
        require_auth(authorization=None, x_user_id=user_id, x_api_key="the-correct-key")
    )
    assert result == user_id
