"""Unit tests for the file upload and storage service."""

import os
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

from app.services.file_upload import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    validate_files,
    store_file,
)


def _make_upload_file(
    filename: str = "test.pdf",
    content: bytes = b"fake pdf content",
    content_type: str = "application/pdf",
) -> UploadFile:
    """Helper to create a mock UploadFile.

    UploadFile.content_type is a read-only property derived from headers,
    so we pass content-type via the headers dict.
    """
    from starlette.datastructures import Headers

    file = UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )
    return file


class TestValidateFiles:
    """Tests for validate_files function."""

    @pytest.mark.asyncio
    async def test_valid_pdf_passes(self):
        """A valid PDF file should pass validation."""
        file = _make_upload_file("doc.pdf", b"pdf bytes", "application/pdf")
        valid, errors = await validate_files([file])
        assert len(valid) == 1
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_valid_csv_passes(self):
        """A valid CSV file should pass validation."""
        file = _make_upload_file("data.csv", b"a,b,c\n1,2,3", "text/csv")
        valid, errors = await validate_files([file])
        assert len(valid) == 1
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_invalid_mime_type_rejected(self):
        """A file with unsupported MIME type should be rejected."""
        file = _make_upload_file("image.png", b"png bytes", "image/png")
        valid, errors = await validate_files([file])
        assert len(valid) == 0
        assert len(errors) == 1
        assert errors[0]["filename"] == "image.png"
        assert "Unsupported file type" in errors[0]["error"]

    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self):
        """A file exceeding MAX_FILE_SIZE should be rejected."""
        large_content = b"x" * (MAX_FILE_SIZE + 1)
        file = _make_upload_file("big.pdf", large_content, "application/pdf")
        valid, errors = await validate_files([file])
        assert len(valid) == 0
        assert len(errors) == 1
        assert errors[0]["filename"] == "big.pdf"
        assert "exceeds maximum" in errors[0]["error"]

    @pytest.mark.asyncio
    async def test_mixed_files_partial_validation(self):
        """Mix of valid and invalid files returns correct split."""
        good_pdf = _make_upload_file("good.pdf", b"pdf", "application/pdf")
        bad_type = _make_upload_file("bad.exe", b"exe", "application/x-msdownload")
        good_csv = _make_upload_file("data.csv", b"a,b\n1,2", "text/csv")

        valid, errors = await validate_files([good_pdf, bad_type, good_csv])
        assert len(valid) == 2
        assert len(errors) == 1
        assert errors[0]["filename"] == "bad.exe"

    @pytest.mark.asyncio
    async def test_empty_file_list(self):
        """An empty file list should return empty results."""
        valid, errors = await validate_files([])
        assert len(valid) == 0
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_file_at_max_size_passes(self):
        """A file exactly at MAX_FILE_SIZE should pass validation."""
        content = b"x" * MAX_FILE_SIZE
        file = _make_upload_file("exact.pdf", content, "application/pdf")
        valid, errors = await validate_files([file])
        assert len(valid) == 1
        assert len(errors) == 0


class TestStoreFileLocal:
    """Tests for store_file with local backend."""

    @pytest.mark.asyncio
    async def test_store_local_creates_file(self, tmp_path, monkeypatch):
        """store_file should create the file on disk in local mode."""
        monkeypatch.chdir(tmp_path)

        mock_settings = MagicMock()
        mock_settings.STORAGE_BACKEND = "local"

        with patch("app.services.file_upload.get_settings", return_value=mock_settings):
            file = _make_upload_file("report.pdf", b"pdf content", "application/pdf")
            path = await store_file(file, "user-1", "job-abc")

        expected = Path("uploads") / "user-1" / "job-abc" / "report.pdf"
        assert path == str(expected)
        assert (tmp_path / expected).exists()
        assert (tmp_path / expected).read_bytes() == b"pdf content"

    @pytest.mark.asyncio
    async def test_store_local_creates_directories(self, tmp_path, monkeypatch):
        """store_file should create nested directories if they don't exist."""
        monkeypatch.chdir(tmp_path)

        mock_settings = MagicMock()
        mock_settings.STORAGE_BACKEND = "local"

        with patch("app.services.file_upload.get_settings", return_value=mock_settings):
            file = _make_upload_file("data.csv", b"a,b\n1,2", "text/csv")
            await store_file(file, "new-user", "new-job")

        assert (tmp_path / "uploads" / "new-user" / "new-job").is_dir()


class TestStoreFileS3:
    """Tests for store_file with S3 backend."""

    @pytest.mark.asyncio
    async def test_store_s3_uploads_to_correct_key(self):
        """store_file should upload to S3 with the correct key."""
        mock_settings = MagicMock()
        mock_settings.STORAGE_BACKEND = "s3"
        mock_settings.S3_REGION = "us-east-1"
        mock_settings.S3_BUCKET_NAME = "test-bucket"
        mock_settings.AWS_ACCESS_KEY_ID = "fake-key"
        mock_settings.AWS_SECRET_ACCESS_KEY = "fake-secret"

        mock_s3 = MagicMock()

        with patch("app.services.file_upload.get_settings", return_value=mock_settings):
            with patch("app.services.file_upload.boto3.client", return_value=mock_s3):
                file = _make_upload_file("doc.pdf", b"content", "application/pdf")
                key = await store_file(file, "user-42", "job-xyz")

        assert key == "user-42/job-xyz/doc.pdf"
        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="user-42/job-xyz/doc.pdf",
            Body=b"content",
            ContentType="application/pdf",
        )
