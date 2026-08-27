"""Tests for avatar storage (local data URI passthrough + S3 presigned URLs)."""

import base64
from unittest.mock import patch

import pytest

from app.services import avatar_storage

PNG_DATA_URI = "data:image/png;base64," + base64.b64encode(b"fake-png-bytes").decode()


# --- Local backend (default) -------------------------------------------------


def test_local_store_returns_data_uri_unchanged():
    assert avatar_storage.store_avatar("u1", PNG_DATA_URI) == PNG_DATA_URI


def test_local_resolve_returns_data_uri_unchanged():
    assert avatar_storage.resolve_avatar_url(PNG_DATA_URI) == PNG_DATA_URI


def test_resolve_none_and_empty_pass_through():
    assert avatar_storage.resolve_avatar_url(None) is None
    assert avatar_storage.resolve_avatar_url("") == ""


def test_local_delete_is_a_noop():
    avatar_storage.delete_avatar(PNG_DATA_URI)  # must not raise


# --- S3 backend (fake client, no boto3/moto) ---------------------------------


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[Key] = Body
        self.content_types[Key] = ContentType

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://{Params['Bucket']}.s3.amazonaws.com/{Params['Key']}?sig=fake&exp={ExpiresIn}"


@pytest.fixture
def fake_s3():
    fake = FakeS3()
    with patch.object(avatar_storage, "_use_s3", return_value=True), \
         patch.object(avatar_storage, "_bucket", return_value="test-bucket"), \
         patch("app.config.database.get_s3_client", return_value=fake):
        yield fake


def test_s3_store_uploads_and_returns_key(fake_s3):
    key = avatar_storage.store_avatar("u1", PNG_DATA_URI)
    assert key == "avatars/u1.png"
    assert fake_s3.objects[key] == b"fake-png-bytes"
    assert fake_s3.content_types[key] == "image/png"


def test_s3_store_rejects_non_data_uri(fake_s3):
    with pytest.raises(ValueError):
        avatar_storage.store_avatar("u1", "https://example.com/pic.png")


def test_s3_resolve_returns_presigned_url(fake_s3):
    url = avatar_storage.resolve_avatar_url("avatars/u1.png")
    assert url.startswith("https://test-bucket.s3.amazonaws.com/avatars/u1.png")
    assert "sig=fake" in url


def test_s3_resolve_none_passes_through(fake_s3):
    assert avatar_storage.resolve_avatar_url(None) is None


def test_s3_delete_removes_object(fake_s3):
    key = avatar_storage.store_avatar("u1", PNG_DATA_URI)
    assert key in fake_s3.objects
    avatar_storage.delete_avatar(key)
    assert key not in fake_s3.objects
