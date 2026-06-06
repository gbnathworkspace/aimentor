"""Property-based tests for file upload validation and S3 path construction.

Uses Hypothesis to verify universal properties across random inputs.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import AsyncMock

from app.services.file_upload_handler import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    FileUploadHandler,
    construct_s3_key,
)


# --- Helpers ---


def _make_mock_upload_file(content: bytes, filename: str, content_type: str):
    """Create a mock UploadFile with the given properties."""
    mock = AsyncMock()
    mock.filename = filename
    mock.content_type = content_type
    mock.read = AsyncMock(return_value=content)
    return mock


# --- Property 1: File upload validation ---
# Feature: ingestion-pipeline, Property 1: File upload validation
# **Validates: Requirements 1.1, 1.2, 1.3, 1.4**


@settings(max_examples=100)
@given(
    mime_type=st.text(min_size=1, max_size=50),
    size=st.integers(min_value=0, max_value=20_000_000),
)
@pytest.mark.asyncio
async def test_file_upload_validation_property(mime_type: str, size: int):
    """For any file upload, validation accepts if and only if MIME type is in
    {'application/pdf', 'text/csv'} AND 0 < size <= 10,485,760.

    This tests the real FileUploadHandler.handle_upload validation logic.
    """
    # Determine expected acceptance based on the property definition
    valid_type = mime_type in ALLOWED_MIME_TYPES
    valid_size = 0 < size <= MAX_FILE_SIZE
    should_accept = valid_type and valid_size

    # Create a mock file with the generated mime_type and size
    content = b"x" * size
    mock_file = _make_mock_upload_file(content, "test_file.dat", mime_type)

    # Exercise the real handler
    handler = FileUploadHandler()
    errors, validated = await handler.handle_upload("test_user", [mock_file])

    # Check actual acceptance matches expected
    actual_accept = errors is None and validated is not None

    assert should_accept == actual_accept, (
        f"mime_type={mime_type!r}, size={size}: "
        f"expected accept={should_accept}, got accept={actual_accept}"
    )


# --- Property 2: S3 path construction ---
# Feature: ingestion-pipeline, Property 2: S3 path construction
# **Validates: Requirements 1.5**


@settings(max_examples=100)
@given(
    user_id=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    job_id=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    filename=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
)
def test_s3_path_construction_property(user_id: str, job_id: str, filename: str):
    """For any valid userId, jobId, and filename, the constructed S3 key equals
    uploads/{userId}/{jobId}/{filename}.

    This tests the real construct_s3_key function.
    """
    result = construct_s3_key(user_id, job_id, filename)
    expected = f"uploads/{user_id}/{job_id}/{filename}"
    assert result == expected
