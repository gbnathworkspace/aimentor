"""Unit tests for app/services/file_cleanup.py — expired upload file cleanup."""

import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.file_cleanup import (
    UPLOADS_BASE_DIR,
    cleanup_expired_uploads,
    delete_upload_files,
)


@pytest.fixture
def temp_uploads(tmp_path, monkeypatch):
    """Create a temporary uploads directory and patch UPLOADS_BASE_DIR."""
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    monkeypatch.setattr(
        "app.services.file_cleanup.UPLOADS_BASE_DIR", uploads_dir
    )
    # delete_upload_files delegates to storage.delete_job_files, which reads
    # its own base dir — patch it too.
    monkeypatch.setattr("app.services.storage.UPLOADS_BASE_DIR", uploads_dir)
    return uploads_dir


def _create_job_dir(uploads_dir: Path, user_id: str, job_id: str) -> Path:
    """Helper to create a job directory with a dummy file."""
    job_dir = uploads_dir / user_id / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "document.pdf").write_text("fake pdf content")
    return job_dir


class TestDeleteUploadFiles:
    """Tests for the delete_upload_files function."""

    def test_deletes_existing_directory(self, temp_uploads):
        """Should delete the job directory and return True."""
        job_dir = _create_job_dir(temp_uploads, "user-1", "job-abc")
        assert job_dir.exists()

        result = delete_upload_files("user-1", "job-abc")

        assert result is True
        assert not job_dir.exists()

    def test_returns_false_for_nonexistent_directory(self, temp_uploads):
        """Should return False when the directory doesn't exist."""
        result = delete_upload_files("user-1", "nonexistent-job")

        assert result is False

    def test_deletes_all_files_in_directory(self, temp_uploads):
        """Should remove all files within the job directory."""
        job_dir = _create_job_dir(temp_uploads, "user-2", "job-xyz")
        # Add more files
        (job_dir / "resume.docx").write_text("fake docx")
        (job_dir / "notes.txt").write_text("notes")

        result = delete_upload_files("user-2", "job-xyz")

        assert result is True
        assert not job_dir.exists()


class TestCleanupExpiredUploads:
    """Tests for the cleanup_expired_uploads function."""

    @pytest.mark.asyncio
    async def test_removes_orphaned_directories(self, temp_uploads):
        """Should remove directories whose job records no longer exist in MongoDB."""
        # Create two job directories
        job_dir_1 = _create_job_dir(temp_uploads, "user-1", "job-expired")
        job_dir_2 = _create_job_dir(temp_uploads, "user-1", "job-active")

        # Mock MongoDB: job-expired not found, job-active found
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(
            side_effect=lambda query, *args, **kwargs: (
                None if query["job_id"] == "job-expired" else {"_id": "some-id"}
            )
        )

        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ):
            removed = await cleanup_expired_uploads()

        assert removed == 1
        assert not job_dir_1.exists()  # orphaned — removed
        assert job_dir_2.exists()  # still in MongoDB — kept

    @pytest.mark.asyncio
    async def test_no_uploads_directory(self, temp_uploads):
        """Should return 0 if the uploads directory doesn't exist."""
        shutil.rmtree(temp_uploads)

        mock_col = AsyncMock()
        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ):
            removed = await cleanup_expired_uploads()

        assert removed == 0
        mock_col.find_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_uploads_directory(self, temp_uploads):
        """Should return 0 when uploads directory is empty."""
        mock_col = AsyncMock()
        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ):
            removed = await cleanup_expired_uploads()

        assert removed == 0

    @pytest.mark.asyncio
    async def test_removes_empty_user_directories(self, temp_uploads):
        """Should remove user directories that become empty after cleanup."""
        _create_job_dir(temp_uploads, "user-lonely", "job-only")

        # The only job is orphaned
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value=None)

        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ):
            removed = await cleanup_expired_uploads()

        assert removed == 1
        # User directory should also be gone (empty after job dir removal)
        assert not (temp_uploads / "user-lonely").exists()

    @pytest.mark.asyncio
    async def test_keeps_user_directory_with_remaining_jobs(self, temp_uploads):
        """Should keep user directory if it still has active job directories."""
        _create_job_dir(temp_uploads, "user-1", "job-expired")
        _create_job_dir(temp_uploads, "user-1", "job-active")

        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(
            side_effect=lambda query, *args, **kwargs: (
                None if query["job_id"] == "job-expired" else {"_id": "x"}
            )
        )

        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ):
            removed = await cleanup_expired_uploads()

        assert removed == 1
        # User directory stays because job-active is still there
        assert (temp_uploads / "user-1").exists()
        assert (temp_uploads / "user-1" / "job-active").exists()

    @pytest.mark.asyncio
    async def test_handles_multiple_users(self, temp_uploads):
        """Should process all user directories."""
        _create_job_dir(temp_uploads, "user-a", "job-1")
        _create_job_dir(temp_uploads, "user-b", "job-2")
        _create_job_dir(temp_uploads, "user-b", "job-3")

        # All orphaned
        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value=None)

        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ):
            removed = await cleanup_expired_uploads()

        assert removed == 3
        # All user directories should be removed too (now empty)
        assert not (temp_uploads / "user-a").exists()
        assert not (temp_uploads / "user-b").exists()

    @pytest.mark.asyncio
    async def test_handles_rmtree_error_gracefully(self, temp_uploads):
        """Should log and continue if a directory removal fails."""
        _create_job_dir(temp_uploads, "user-1", "job-err")
        _create_job_dir(temp_uploads, "user-1", "job-ok")

        mock_col = AsyncMock()
        mock_col.find_one = AsyncMock(return_value=None)

        real_rmtree = shutil.rmtree

        def mock_rmtree(path, *args, **kwargs):
            if "job-err" in str(path):
                raise OSError("Permission denied")
            real_rmtree(path)

        with patch(
            "app.services.file_cleanup.document_upload_jobs_col",
            return_value=mock_col,
        ), patch(
            "app.services.file_cleanup.shutil.rmtree",
            side_effect=mock_rmtree,
        ):
            removed = await cleanup_expired_uploads()

        # Only the successful removal is counted
        assert removed == 1
