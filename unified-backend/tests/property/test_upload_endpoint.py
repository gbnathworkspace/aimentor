# Feature: chat-document-upload, Property 3: Server-side batch validation accepts valid subset and rejects invalid
"""Property test — server-side batch validation accepts valid subset and rejects invalid.

For any upload request containing a list of files with random sizes, MIME types,
and count, the endpoint SHALL:
  (a) reject the entire request with 400 if count > 5,
  (b) return 400 if all files fail individual validation,
  (c) return 202 with the correct acceptedFiles count and rejectedFiles list
      if at least one file passes validation.

**Validates: Requirements 2.3, 2.4, 2.5, 2.6**
"""

import io
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.routers.documents import SUPPORTED_MIME_TYPES, MAX_FILES, MAX_FILE_SIZE_BYTES

# --- Strategies ---

VALID_MIME_TYPES = list(SUPPORTED_MIME_TYPES)
INVALID_MIME_TYPES = [
    "image/png",
    "image/jpeg",
    "application/x-msdownload",
    "video/mp4",
    "audio/mpeg",
    "application/octet-stream",
    "text/html",
    "application/zip",
]

ALL_MIME_TYPES = VALID_MIME_TYPES + INVALID_MIME_TYPES


def file_strategy():
    """Generate a random file descriptor: (filename, content_bytes, mime_type)."""
    # Use safe characters for filenames — exclude path separators and special OS chars
    safe_chars = st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-_.",
    )
    return st.tuples(
        st.text(alphabet=safe_chars, min_size=1, max_size=30).map(lambda s: s + ".bin"),
        # File sizes from 1 byte to 20 MB (covering valid and oversized)
        st.integers(min_value=1, max_value=20 * 1024 * 1024),
        st.sampled_from(ALL_MIME_TYPES),
    )


def batch_strategy():
    """Generate a random batch of 0–10 files."""
    return st.lists(file_strategy(), min_size=0, max_size=10)


# --- Helpers ---

def _classify_file(size: int, mime: str) -> bool:
    """Return True if the file would pass server-side validation."""
    return mime in SUPPORTED_MIME_TYPES and size <= MAX_FILE_SIZE_BYTES


def _make_multipart_files(batch: list[tuple[str, int, str]]) -> list[tuple[str, tuple]]:
    """Convert batch descriptors into httpx-compatible multipart file tuples.

    For efficiency in property tests, we cap actual content at a small size
    but set Content-Length via header manipulation. The endpoint reads content
    to determine size, so we generate actual content of the specified size
    for small files and use a truncated approach for large files to avoid
    memory issues during testing.
    """
    files = []
    for filename, size, mime in batch:
        # For property testing: generate small representative content for
        # files under the limit, and just-over-limit content for large files.
        # The endpoint reads file.read() to check size, so we need actual bytes.
        if size <= MAX_FILE_SIZE_BYTES:
            # Valid-sized file: use minimal content matching the exact size
            # Cap at 1KB for speed — the endpoint checks len(content)
            actual_content = b"x" * min(size, 1024)
        else:
            # Oversized file: produce content that exceeds the limit
            actual_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        files.append(("files", (filename, io.BytesIO(actual_content), mime)))
    return files


# --- Property Test ---


@settings(max_examples=100, deadline=None)
@given(batch=batch_strategy())
@pytest.mark.asyncio
async def test_server_batch_validation_partition(batch):
    """Property 3: Server-side batch validation accepts valid subset and rejects invalid.

    **Validates: Requirements 2.3, 2.4, 2.5, 2.6**
    """
    # Skip empty batches — FastAPI requires at least one file in the files field
    assume(len(batch) > 0)

    # Classify files according to validation rules
    num_files = len(batch)

    # For files that are under the size limit, we use min(size, 1024) as actual
    # content — so we must classify based on actual_content_size for the test
    expected_valid = []
    expected_invalid = []
    for filename, size, mime in batch:
        if size <= MAX_FILE_SIZE_BYTES:
            actual_size = min(size, 1024)
        else:
            actual_size = MAX_FILE_SIZE_BYTES + 1

        if mime in SUPPORTED_MIME_TYPES and actual_size <= MAX_FILE_SIZE_BYTES:
            expected_valid.append(filename)
        else:
            expected_invalid.append(filename)

    # Mock auth dependency to return a fixed user_id
    async def mock_require_auth():
        return "test-user-property"

    # Mock MongoDB collection insert_one
    mock_col = AsyncMock()
    mock_col.insert_one = AsyncMock(return_value=AsyncMock(inserted_id="fake_id"))

    from app.main import app
    from app.auth.dependencies import require_auth

    # Override the auth dependency
    app.dependency_overrides[require_auth] = mock_require_auth

    # Use a temporary directory for file uploads to avoid polluting the workspace
    tmp_dir = tempfile.mkdtemp()

    try:
        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_col),
            patch("app.routers.documents.process_document_upload", new_callable=AsyncMock),
            patch("app.routers.documents.UPLOADS_BASE_DIR", Path(tmp_dir)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                multipart_files = _make_multipart_files(batch)

                response = await client.post(
                    "/api/documents/upload",
                    files=multipart_files,
                    data={"skip_review": "false"},
                )

                # Assert the three-way partition
                if num_files > MAX_FILES:
                    # (a) Batch exceeds limit → 400
                    assert response.status_code == 400, (
                        f"Expected 400 for batch of {num_files} files, "
                        f"got {response.status_code}"
                    )
                    detail = response.json()["detail"]
                    assert "Maximum batch size" in detail or "maximum" in detail.lower()

                elif len(expected_valid) == 0:
                    # (b) All files invalid → 400 with per-file errors
                    assert response.status_code == 400, (
                        f"Expected 400 when all files invalid, "
                        f"got {response.status_code}: {response.json()}"
                    )
                    detail = response.json()["detail"]
                    assert "errors" in detail
                    assert len(detail["errors"]) == len(batch)

                else:
                    # (c) At least one valid → 202 with correct counts
                    assert response.status_code == 202, (
                        f"Expected 202 with {len(expected_valid)} valid files, "
                        f"got {response.status_code}: {response.json()}"
                    )
                    body = response.json()
                    assert body["acceptedFiles"] == len(expected_valid), (
                        f"Expected acceptedFiles={len(expected_valid)}, "
                        f"got {body['acceptedFiles']}"
                    )
                    assert len(body["rejectedFiles"]) == len(expected_invalid), (
                        f"Expected {len(expected_invalid)} rejectedFiles, "
                        f"got {len(body['rejectedFiles'])}"
                    )
                    # Verify jobId is present
                    assert "jobId" in body
                    assert len(body["jobId"]) > 0
    finally:
        # Clean up dependency override and temp directory
        app.dependency_overrides.pop(require_auth, None)
        shutil.rmtree(tmp_dir, ignore_errors=True)
