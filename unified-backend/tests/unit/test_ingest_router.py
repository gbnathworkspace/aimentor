"""Unit tests for app/routers/ingest.py — Ingestion endpoints."""

import os
from io import BytesIO
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
def mock_ingestion_col():
    """Provide a mocked ingestion_jobs_col with async methods."""
    col = MagicMock()
    col.find_one = AsyncMock()
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    return col


class TestUploadFiles:
    """POST /api/ingest — upload files and create ingestion job."""

    @pytest.mark.asyncio
    async def test_upload_valid_pdf_returns_201(self, auth_headers, mock_ingestion_col):
        """Upload a valid PDF file returns 201 with job_id."""
        valid_files = [MagicMock()]
        errors = []

        with (
            patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col),
            patch("app.routers.ingest.validate_files", new_callable=AsyncMock, return_value=(valid_files, errors)),
            patch("app.routers.ingest.store_file", new_callable=AsyncMock, return_value="/uploads/user-123/job-1/test.pdf"),
            patch("app.routers.ingest.process_extraction"),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest",
                    headers=auth_headers,
                    files={"files": ("test.pdf", BytesIO(b"%PDF-fake-content"), "application/pdf")},
                )

        assert resp.status_code == 201
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "processing"
        assert "message" in data

    @pytest.mark.asyncio
    async def test_upload_all_invalid_files_returns_400(self, auth_headers, mock_ingestion_col):
        """Upload of only invalid files returns 400 with errors."""
        valid_files = []
        errors = [{"filename": "test.exe", "error": "Unsupported file type"}]

        with (
            patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col),
            patch("app.routers.ingest.validate_files", new_callable=AsyncMock, return_value=(valid_files, errors)),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest",
                    headers=auth_headers,
                    files={"files": ("test.exe", BytesIO(b"MZ-fake"), "application/x-msdownload")},
                )

        assert resp.status_code == 400
        data = resp.json()
        assert "errors" in data["detail"]

    @pytest.mark.asyncio
    async def test_upload_mixed_valid_invalid_returns_201(self, auth_headers, mock_ingestion_col):
        """Upload with some valid and some invalid files still returns 201."""
        valid_file = MagicMock()
        valid_file.filename = "good.pdf"
        errors = [{"filename": "bad.exe", "error": "Unsupported file type"}]

        with (
            patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col),
            patch("app.routers.ingest.validate_files", new_callable=AsyncMock, return_value=([valid_file], errors)),
            patch("app.routers.ingest.store_file", new_callable=AsyncMock, return_value="/uploads/user-123/job-1/good.pdf"),
            patch("app.routers.ingest.process_extraction"),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest",
                    headers=auth_headers,
                    files=[
                        ("files", ("good.pdf", BytesIO(b"%PDF-content"), "application/pdf")),
                        ("files", ("bad.exe", BytesIO(b"MZ"), "application/x-msdownload")),
                    ],
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_upload_no_files_returns_400(self, auth_headers, mock_ingestion_col):
        """Upload with empty file list returns 400."""
        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Send a POST with no files field — FastAPI will return 422
                resp = await client.post(
                    "/api/ingest",
                    headers=auth_headers,
                )

        # FastAPI returns 422 for missing required field
        assert resp.status_code == 422


class TestGetJobStatus:
    """GET /api/ingest/{job_id}/status — get job status."""

    @pytest.mark.asyncio
    async def test_returns_job_status(self, auth_headers, mock_ingestion_col):
        """Existing job returns its status."""
        mock_ingestion_col.find_one = AsyncMock(return_value={
            "job_id": "job-abc",
            "user_id": "user-123",
            "status": "completed",
            "completed_at": "2024-01-01T00:00:00Z",
        })

        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/ingest/job-abc/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["jobId"] == "job-abc"
        assert data["status"] == "completed"
        assert data["completedAt"] == "2024-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_job(self, auth_headers, mock_ingestion_col):
        """Non-existent job returns 404."""
        mock_ingestion_col.find_one = AsyncMock(return_value=None)

        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/ingest/nonexistent/status", headers=auth_headers)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_403_for_other_users_job(self, auth_headers, mock_ingestion_col):
        """Job owned by another user returns 403."""
        mock_ingestion_col.find_one = AsyncMock(return_value={
            "job_id": "job-xyz",
            "user_id": "other-user-456",
            "status": "processing",
        })

        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/ingest/job-xyz/status", headers=auth_headers)

        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"].lower()


class TestTriggerExtraction:
    """POST /api/ingest/trigger — re-trigger extraction for a job."""

    @pytest.mark.asyncio
    async def test_trigger_enqueues_extraction(self, auth_headers, mock_ingestion_col):
        """Valid trigger re-enqueues extraction and returns processing."""
        mock_ingestion_col.find_one = AsyncMock(return_value={
            "job_id": "job-abc",
            "user_id": "user-123",
            "status": "failed",
            "file_paths": ["/uploads/user-123/job-abc/test.pdf"],
        })

        with (
            patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col),
            patch("app.routers.ingest.process_extraction"),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest/trigger",
                    headers=auth_headers,
                    json={"job_id": "job-abc"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-abc"
        assert data["status"] == "processing"
        mock_ingestion_col.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_returns_404_for_missing_job(self, auth_headers, mock_ingestion_col):
        """Trigger for non-existent job returns 404."""
        mock_ingestion_col.find_one = AsyncMock(return_value=None)

        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest/trigger",
                    headers=auth_headers,
                    json={"job_id": "nonexistent"},
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_returns_403_for_other_users_job(self, auth_headers, mock_ingestion_col):
        """Trigger for another user's job returns 403."""
        mock_ingestion_col.find_one = AsyncMock(return_value={
            "job_id": "job-xyz",
            "user_id": "other-user-456",
            "status": "completed",
            "file_paths": ["/uploads/other/job-xyz/test.pdf"],
        })

        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest/trigger",
                    headers=auth_headers,
                    json={"job_id": "job-xyz"},
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_trigger_returns_400_for_no_file_paths(self, auth_headers, mock_ingestion_col):
        """Trigger for job with no file paths returns 400."""
        mock_ingestion_col.find_one = AsyncMock(return_value={
            "job_id": "job-empty",
            "user_id": "user-123",
            "status": "failed",
            "file_paths": [],
        })

        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest/trigger",
                    headers=auth_headers,
                    json={"job_id": "job-empty"},
                )

        assert resp.status_code == 400


class TestAuthEnforcement:
    """Verify auth is enforced on all ingest endpoints."""

    @pytest.mark.asyncio
    async def test_upload_missing_auth_returns_401(self, mock_ingestion_col):
        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest",
                    files={"files": ("test.pdf", BytesIO(b"%PDF"), "application/pdf")},
                )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_status_missing_auth_returns_401(self, mock_ingestion_col):
        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/ingest/job-abc/status")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_trigger_missing_auth_returns_401(self, mock_ingestion_col):
        with patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingestion_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/ingest/trigger",
                    json={"job_id": "job-abc"},
                )

        assert resp.status_code == 401
