"""File storage abstraction: local disk (dev) or S3 (prod).

Selected by settings.STORAGE_BACKEND ('local' | 's3'). In production the S3
client uses the EC2 instance's IAM role (see get_s3_client), so no AWS keys
are stored anywhere.

The `storage_key` returned by store_file is opaque: a filesystem path for the
local backend, an S3 object key for s3. It is what gets persisted as
UploadFileRecord.file_path and passed back to open_for_read.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Base directory for the local backend (matches file_cleanup).
UPLOADS_BASE_DIR = Path("uploads")


def _use_s3() -> bool:
    return get_settings().STORAGE_BACKEND == "s3"


def _bucket() -> str:
    bucket = get_settings().S3_BUCKET_NAME
    if not bucket:
        raise RuntimeError("STORAGE_BACKEND=s3 but S3_BUCKET_NAME is not set")
    return bucket


def store_file(user_id: str, job_id: str, filename: str, content: bytes) -> str:
    """Store file bytes and return an opaque storage key.

    Local: writes uploads/{user_id}/{job_id}/{filename}, returns the path.
    S3: puts object key {user_id}/{job_id}/{filename}, returns the key.
    """
    if _use_s3():
        from app.config.database import get_s3_client

        key = f"{user_id}/{job_id}/{filename}"
        get_s3_client().put_object(Bucket=_bucket(), Key=key, Body=content)
        return key

    upload_dir = UPLOADS_BASE_DIR / user_id / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
    path.write_bytes(content)
    return str(path)


@contextmanager
def open_for_read(storage_key: str) -> Iterator[str]:
    """Yield a local filesystem path for reading a stored file.

    Local: yields storage_key unchanged. S3: downloads to a temp file, yields
    its path, and removes it on exit. This keeps the format extractors purely
    path-based regardless of backend.
    """
    if not _use_s3():
        yield storage_key
        return

    from app.config.database import get_s3_client

    suffix = os.path.splitext(storage_key)[1]
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        get_s3_client().download_file(_bucket(), storage_key, tmp_path)
        yield tmp_path
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def delete_job_files(user_id: str, job_id: str) -> bool:
    """Delete all stored files for a job. Returns True if anything existed."""
    if _use_s3():
        from app.config.database import get_s3_client

        client = get_s3_client()
        prefix = f"{user_id}/{job_id}/"
        resp = client.list_objects_v2(Bucket=_bucket(), Prefix=prefix)
        objects = [{"Key": o["Key"]} for o in resp.get("Contents", [])]
        if not objects:
            return False
        client.delete_objects(Bucket=_bucket(), Delete={"Objects": objects})
        return True

    job_dir = UPLOADS_BASE_DIR / user_id / job_id
    if job_dir.is_dir():
        shutil.rmtree(job_dir)
        return True
    return False
