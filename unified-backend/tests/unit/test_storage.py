"""Tests for the storage backend abstraction (local disk + S3)."""

from unittest.mock import patch

import pytest

from app.services import storage


# --- Local backend (default) -------------------------------------------------


def test_local_roundtrip_and_delete(tmp_path, monkeypatch):
    """store_file → open_for_read → delete_job_files on local disk."""
    monkeypatch.setattr(storage, "UPLOADS_BASE_DIR", tmp_path / "uploads")

    key = storage.store_file("u1", "j1", "notes.txt", b"hello world")
    assert key.endswith("notes.txt")

    with storage.open_for_read(key) as local_path:
        with open(local_path, "rb") as f:
            assert f.read() == b"hello world"

    assert storage.delete_job_files("u1", "j1") is True
    assert storage.delete_job_files("u1", "j1") is False  # already gone


# --- S3 backend (fake client, no boto3/moto) ---------------------------------


class FakeS3:
    """Minimal in-memory stand-in for the boto3 S3 client."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body

    def download_file(self, Bucket, Key, filename):
        with open(filename, "wb") as f:
            f.write(self.objects[Key])

    def list_objects_v2(self, Bucket, Prefix):
        keys = [k for k in self.objects if k.startswith(Prefix)]
        return {"Contents": [{"Key": k} for k in keys]} if keys else {}

    def delete_objects(self, Bucket, Delete):
        for obj in Delete["Objects"]:
            self.objects.pop(obj["Key"], None)


@pytest.fixture
def fake_s3():
    fake = FakeS3()
    with patch.object(storage, "_use_s3", return_value=True), \
         patch.object(storage, "_bucket", return_value="test-bucket"), \
         patch("app.config.database.get_s3_client", return_value=fake):
        yield fake


def test_s3_roundtrip_and_delete(fake_s3):
    """S3 branch: key layout, temp-file read, prefix delete."""
    key = storage.store_file("u1", "j1", "resume.pdf", b"PDFDATA")
    assert key == "u1/j1/resume.pdf"
    assert fake_s3.objects[key] == b"PDFDATA"

    with storage.open_for_read(key) as local_path:
        with open(local_path, "rb") as f:
            assert f.read() == b"PDFDATA"
        temp_path = local_path
    import os
    assert not os.path.exists(temp_path)  # temp file cleaned up on exit

    assert storage.delete_job_files("u1", "j1") is True
    assert key not in fake_s3.objects
    assert storage.delete_job_files("u1", "j1") is False


def test_s3_bucket_unset_raises(monkeypatch):
    """s3 backend without a bucket name fails loudly, not silently."""
    from types import SimpleNamespace

    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(S3_BUCKET_NAME=None))
    with pytest.raises(RuntimeError, match="S3_BUCKET_NAME"):
        storage._bucket()
