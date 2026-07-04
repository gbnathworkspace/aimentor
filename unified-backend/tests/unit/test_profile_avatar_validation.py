"""Unit tests for the avatar data-URI validation guard in the profile router."""

import pytest
from fastapi import HTTPException

from app.routers.profile import _validate_avatar


def test_none_is_allowed():
    _validate_avatar(None)  # no-op, must not raise


def test_empty_string_clears_avatar():
    _validate_avatar("")  # no-op, must not raise


def test_valid_image_data_uri_is_allowed():
    _validate_avatar("data:image/png;base64,aGVsbG8=")


def test_non_image_data_uri_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_avatar("data:text/html,<script>alert(1)</script>")
    assert exc.value.status_code == 400


def test_oversized_avatar_is_rejected():
    huge = "data:image/png;base64," + ("a" * 3_000_000)
    with pytest.raises(HTTPException) as exc:
        _validate_avatar(huge)
    assert exc.value.status_code == 400
