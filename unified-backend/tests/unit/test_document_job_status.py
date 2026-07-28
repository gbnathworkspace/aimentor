"""Unit tests for GET /api/documents/jobs/{job_id}/status endpoint."""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _setup_settings():
    """Ensure get_settings returns predictable config for all tests."""
    get_settings.cache_clear()
    env = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "DATABASE_NAME": "mentorman_test",
        "MENTORMAN_API_KEY": "test-api-key",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "VOYAGE_API_KEY": "voy-test",
    }
    with patch.dict(os.environ, env, clear=True):
        get_settings()
        yield
    get_settings.cache_clear()


@pytest.fixture
def auth_headers():
    return {"X-User-Id": "user-123", "X-Api-Key": "test-api-key"}


@pytest.fixture
def mock_doc_col():
    """Provide a mocked document_upload_jobs_col with async methods."""
    col = MagicMock()
    col.find_one = AsyncMock()
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    return col


class TestGetJobStatus:
    """GET /api/documents/jobs/{job_id}/status — poll upload job status."""

    @pytest.mark.asyncio
    async def test_returns_status_for_pending_job(self, auth_headers, mock_doc_col):
        """A pending job returns correct status and file info."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-001",
            "user_id": "user-123",
            "status": "pending",
            "files": [
                {"filename": "resume.pdf", "status": "pending", "error": None},
                {"filename": "notes.docx", "status": "pending", "error": None},
            ],
            "proposals": None,
            "proposal_count": 0,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-001/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["jobId"] == "job-001"
        assert data["status"] == "pending"
        assert len(data["files"]) == 2
        assert data["files"][0] == {"filename": "resume.pdf", "status": "pending"}
        assert data["proposals"] is None
        assert data["failedFiles"] == []
        assert data["proposalCount"] == 0
        assert data["createdAt"] == "2026-07-23T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_returns_status_for_extracting_job(self, auth_headers, mock_doc_col):
        """An extracting job shows per-file extraction statuses."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-002",
            "user_id": "user-123",
            "status": "extracting",
            "files": [
                {"filename": "resume.pdf", "status": "extracted", "error": None},
                {"filename": "notes.docx", "status": "pending", "error": None},
            ],
            "proposals": None,
            "proposal_count": 0,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-002/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "extracting"
        assert data["files"][0] == {"filename": "resume.pdf", "status": "extracted"}
        assert data["files"][1] == {"filename": "notes.docx", "status": "pending"}
        assert data["proposals"] is None

    @pytest.mark.asyncio
    async def test_returns_proposals_when_done(self, auth_headers, mock_doc_col):
        """A done job returns proposals and proposal count."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        proposals = [
            {
                "field": "focus_areas",
                "proposedValue": "Machine Learning",
                "reason": "Mentioned frequently in resume",
                "sourceFilename": "resume.pdf",
            }
        ]
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-003",
            "user_id": "user-123",
            "status": "done",
            "files": [
                {"filename": "resume.pdf", "status": "extracted", "error": None},
            ],
            "proposals": proposals,
            "proposal_count": 1,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-003/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert data["proposals"] == proposals
        assert data["proposalCount"] == 1

    @pytest.mark.asyncio
    async def test_proposals_null_when_not_done(self, auth_headers, mock_doc_col):
        """A synthesizing job returns proposals as null even if stored on record."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-004",
            "user_id": "user-123",
            "status": "synthesizing",
            "files": [
                {"filename": "resume.pdf", "status": "extracted", "error": None},
            ],
            "proposals": [{"field": "focus_areas", "proposedValue": "ML"}],
            "proposal_count": 1,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-004/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "synthesizing"
        assert data["proposals"] is None

    @pytest.mark.asyncio
    async def test_failed_files_derived_from_file_status(self, auth_headers, mock_doc_col):
        """Failed files are derived from files with status='failed'."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-005",
            "user_id": "user-123",
            "status": "done",
            "files": [
                {"filename": "resume.pdf", "status": "extracted", "error": None},
                {"filename": "corrupted.xlsx", "status": "failed", "error": "File could not be read"},
                {"filename": "empty.txt", "status": "failed", "error": "no extractable content"},
            ],
            "proposals": [{"field": "focus_areas", "proposedValue": "Python"}],
            "proposal_count": 1,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-005/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["failedFiles"]) == 2
        assert data["failedFiles"][0] == {"filename": "corrupted.xlsx", "reason": "File could not be read"}
        assert data["failedFiles"][1] == {"filename": "empty.txt", "reason": "no extractable content"}

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_job(self, auth_headers, mock_doc_col):
        """Non-existent job returns 404."""
        mock_doc_col.find_one = AsyncMock(return_value=None)

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/nonexistent/status", headers=auth_headers)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_403_for_other_users_job(self, auth_headers, mock_doc_col):
        """Job owned by another user returns 403."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-006",
            "user_id": "other-user-456",
            "status": "pending",
            "files": [],
            "proposals": None,
            "proposal_count": 0,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-006/status", headers=auth_headers)

        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_401_without_auth(self, mock_doc_col):
        """Request without authentication returns 401."""
        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-001/status")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_failed_job_returns_status_and_files(self, auth_headers, mock_doc_col):
        """A failed job returns its status with file failures."""
        created = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-007",
            "user_id": "user-123",
            "status": "failed",
            "files": [
                {"filename": "resume.pdf", "status": "extracted", "error": None},
                {"filename": "bad.pdf", "status": "failed", "error": "password-protected"},
            ],
            "proposals": None,
            "proposal_count": 0,
            "created_at": created,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/documents/jobs/job-007/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["proposals"] is None
        assert len(data["failedFiles"]) == 1
        assert data["failedFiles"][0] == {"filename": "bad.pdf", "reason": "password-protected"}
