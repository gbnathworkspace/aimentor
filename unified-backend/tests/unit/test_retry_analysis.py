"""Unit tests for POST /api/documents/jobs/{job_id}/retry-analysis endpoint."""

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


class TestRetryAnalysis:
    """POST /api/documents/jobs/{job_id}/retry-analysis — retry LLM synthesis."""

    @pytest.mark.asyncio
    async def test_returns_202_for_valid_retry(self, auth_headers, mock_doc_col):
        """A failed job with extracted text can be retried, returns 202."""
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-001",
            "user_id": "user-123",
            "status": "failed",
            "extracted_text": "Some extracted document text for synthesis.",
            "skip_review": False,
            "files": [{"filename": "resume.pdf", "status": "extracted", "error": None}],
            "proposals": None,
            "proposal_count": 0,
        })

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col),
            patch("app.routers.documents._run_retry_synthesis", new_callable=AsyncMock) as mock_retry,
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/job-001/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 202
        data = resp.json()
        assert data["jobId"] == "job-001"
        assert data["status"] == "synthesizing"
        assert "message" in data

        # Verify status was updated to synthesizing
        mock_doc_col.update_one.assert_called_once()
        call_args = mock_doc_col.update_one.call_args
        assert call_args[0][0] == {"job_id": "job-001"}
        assert call_args[0][1]["$set"]["status"] == "synthesizing"

        # Verify the background task was scheduled with correct args
        mock_retry.assert_called_once_with(
            job_id="job-001",
            user_id="user-123",
            extracted_text="Some extracted document text for synthesis.",
            skip_review=False,
        )

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_job(self, auth_headers, mock_doc_col):
        """Non-existent job returns 404."""
        mock_doc_col.find_one = AsyncMock(return_value=None)

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/nonexistent/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_403_for_other_users_job(self, auth_headers, mock_doc_col):
        """Job owned by another user returns 403."""
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-002",
            "user_id": "other-user-456",
            "status": "failed",
            "extracted_text": "Some text",
            "skip_review": False,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/job-002/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_409_when_job_not_failed(self, auth_headers, mock_doc_col):
        """Job not in 'failed' state returns 409 conflict."""
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-003",
            "user_id": "user-123",
            "status": "done",
            "extracted_text": "Some text",
            "skip_review": False,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/job-003/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 409
        assert "retry is only available for failed jobs" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_409_when_job_is_synthesizing(self, auth_headers, mock_doc_col):
        """Job in 'synthesizing' state returns 409 conflict."""
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-004",
            "user_id": "user-123",
            "status": "synthesizing",
            "extracted_text": "Some text",
            "skip_review": False,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/job-004/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_400_when_no_extracted_text(self, auth_headers, mock_doc_col):
        """Failed job with no extracted_text returns 400."""
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-005",
            "user_id": "user-123",
            "status": "failed",
            "extracted_text": None,
            "skip_review": False,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/job-005/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 400
        assert "no extracted text" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_400_when_extracted_text_is_empty_string(self, auth_headers, mock_doc_col):
        """Failed job with empty string extracted_text returns 400."""
        mock_doc_col.find_one = AsyncMock(return_value={
            "job_id": "job-006",
            "user_id": "user-123",
            "status": "failed",
            "extracted_text": "",
            "skip_review": False,
        })

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/documents/jobs/job-006/retry-analysis",
                    headers=auth_headers,
                )

        assert resp.status_code == 400
        assert "no extracted text" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_401_without_auth(self, mock_doc_col):
        """Request without authentication returns 401."""
        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/documents/jobs/job-001/retry-analysis")

        assert resp.status_code == 401
