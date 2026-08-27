"""Avatar storage: S3 (prod, presigned URLs) or inline data URI (local dev).

Selected by settings.STORAGE_BACKEND, mirroring app/services/storage.py's
split for document uploads. Avatars are personal photos with no reason to
be publicly reachable, so the S3 path never makes objects public — every
read goes through a short-lived presigned URL instead of a bucket policy
or object ACL.
"""

from __future__ import annotations

import base64
import binascii
import re

from app.config.settings import get_settings

_PRESIGN_EXPIRES_SECONDS = 3600
_DATA_URI_RE = re.compile(r"^data:image/(?P<subtype>[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$", re.DOTALL)
_EXT_BY_SUBTYPE = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp", "gif": "gif"}


def _use_s3() -> bool:
    return get_settings().STORAGE_BACKEND == "s3"


def _bucket() -> str:
    bucket = get_settings().S3_BUCKET_NAME
    if not bucket:
        raise RuntimeError("STORAGE_BACKEND=s3 but S3_BUCKET_NAME is not set")
    return bucket


def store_avatar(user_id: str, data_uri: str) -> str:
    """Persist an avatar from an uploaded data URI. Returns the value to save
    on the user doc — an S3 object key when S3-backed, or the data URI
    unchanged for local dev (already validated by _validate_avatar upstream).
    """
    if not _use_s3():
        return data_uri

    match = _DATA_URI_RE.match(data_uri)
    if not match:
        raise ValueError("Avatar must be an image data URI")
    ext = _EXT_BY_SUBTYPE.get(match.group("subtype").lower(), "png")
    try:
        content = base64.b64decode(match.group("data"), validate=True)
    except binascii.Error as e:
        raise ValueError("Avatar data URI is not valid base64") from e

    from app.config.database import get_s3_client

    # ponytail: one key per user, overwritten on every upload — no orphan
    # cleanup needed. If the content-type changes across uploads, the old
    # extension's object is left behind; not worth tracking for a single
    # profile picture.
    key = f"avatars/{user_id}.{ext}"
    get_s3_client().put_object(
        Bucket=_bucket(), Key=key, Body=content, ContentType=f"image/{match.group('subtype')}"
    )
    return key


def resolve_avatar_url(stored_value: str | None) -> str | None:
    """Turn a stored avatar value into something the browser can load.

    S3-backed: stored_value is an object key -> presigned GET URL (~1hr).
    Local dev: stored_value is already a data URI -> returned unchanged.
    """
    if not stored_value:
        return stored_value
    if not _use_s3() or stored_value.startswith("data:"):
        return stored_value

    from app.config.database import get_s3_client

    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": stored_value},
        ExpiresIn=_PRESIGN_EXPIRES_SECONDS,
    )


def delete_avatar(stored_value: str | None) -> None:
    """Best-effort delete of the S3 object backing a cleared/replaced avatar."""
    if not stored_value or not _use_s3() or stored_value.startswith("data:"):
        return
    from app.config.database import get_s3_client

    get_s3_client().delete_object(Bucket=_bucket(), Key=stored_value)
