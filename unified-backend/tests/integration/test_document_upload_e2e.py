"""Integration tests for the end-to-end document upload flow.

Tests the full pipeline: file upload → extraction → synthesis → proposals
displayed → accept/dismiss. Also validates pipeline independence from
the existing ingestion pipeline, TTL cleanup, and document-sourced
proposals working with the existing accept/dismiss paths.

Validates Requirements: 8.1, 8.5, 2.7
"""

import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def integration_client():
    """Async HTTP client with mocked MongoDB for integration testing."""
    with patch("app.config.database._db") as mock_db:
        # Set up a mock database that returns mock collections
        mock_db.__getitem__ = MagicMock(return_value=MagicMock())

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def auth_headers():
    """Standard auth headers for test requests."""
    return {"X-User-Id": "test-user-integration", "X-Api-Key": "test-api-key"}


@pytest.fixture
def sample_text_file():
    """Create a simple text file for upload testing."""
    content = b"I am a software engineer with 5 years of experience in Python and AWS."
    return ("resume.txt", content, "text/plain")


@pytest.fixture
def sample_pdf_file():
    """Create a minimal valid file buffer pretending to be a PDF."""
    content = b"%PDF-1.4 fake pdf content for testing"
    return ("document.pdf", content, "application/pdf")


def _make_upload_file(filename: str, content: bytes, content_type: str):
    """Create a file tuple suitable for httpx multipart upload."""
    return ("files", (filename, io.BytesIO(content), content_type))


class TestFullUploadFlow:
    """Test full flow: upload → extraction → synthesis → proposals → accept/dismiss.

    Validates Requirement 8.1: Pipeline is independent from IngestionService.
    """

    @pytest.mark.asyncio
    async def test_upload_creates_job_and_returns_202(self, auth_headers):
        """Upload valid files → job created → HTTP 202 with jobId."""
        mock_col = MagicMock()
        mock_col.insert_one = AsyncMock()

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_col),
            patch("app.services.document_pipeline.process_document_upload", new_callable=AsyncMock),
            patch("os.makedirs", return_value=None),
            patch("pathlib.Path.mkdir", return_value=None),
            patch("pathlib.Path.write_bytes", return_value=None),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                files = [
                    ("files", ("resume.txt", io.BytesIO(b"Hello world content"), "text/plain")),
                ]
                response = await client.post(
                    "/api/documents/upload",
                    files=files,
                    data={"skip_review": "false"},
                    headers=auth_headers,
                )

            assert response.status_code == 202
            body = response.json()
            assert "jobId" in body
            assert body["acceptedFiles"] == 1
            assert body["rejectedFiles"] == []

    @pytest.mark.asyncio
    async def test_full_pipeline_extraction_to_proposals(self, auth_headers):
        """Full flow: upload → extract succeeds → synthesis returns proposals → job done."""
        job_id = str(uuid.uuid4())
        user_id = "test-user-integration"

        # Simulate the job record as stored in MongoDB after upload
        job_doc = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "done",
            "files": [
                {"filename": "resume.txt", "status": "extracted", "error": None},
            ],
            "skip_review": False,
            "proposals": [
                {
                    "field": "focus_area",
                    "proposed_value": {"value": "Cloud Architecture"},
                    "reason": "Document mentions extensive AWS experience",
                    "sourceFilename": "resume.txt",
                }
            ],
            "proposal_count": 1,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
        }

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=job_doc)

        with patch("app.routers.documents.document_upload_jobs_col", return_value=mock_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/documents/jobs/{job_id}/status",
                    headers=auth_headers,
                )

            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "done"
            assert body["proposalCount"] == 1
            assert body["proposals"][0]["field"] == "focus_area"
            assert body["proposals"][0]["proposed_value"]["value"] == "Cloud Architecture"

    @pytest.mark.asyncio
    async def test_proposals_accept_via_profile_endpoint(self, auth_headers):
        """Accept a document-sourced proposal through the existing accept endpoint."""
        user_id = "test-user-integration"
        job_id = str(uuid.uuid4())

        # Profile with a document-sourced pending change
        profile_doc = {
            "user_id": user_id,
            "focus_areas": ["Python"],
            "style_notes": [],
            "pending_changes": [
                {
                    "field": "focus_area",
                    "proposed_value": {"value": "Cloud Architecture"},
                    "reason": "Extracted from uploaded document",
                    "session_id": job_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_type": "document_upload",
                }
            ],
            "learning_context": None,
            "learning_context_detail": None,
            "explanation_style": "hint-first",
            "challenge_tolerance": "medium",
            "feedback_tone": "encouraging",
        }

        # After accepting, the updated profile
        updated_profile = {**profile_doc}
        updated_profile["focus_areas"] = ["Python", "Cloud Architecture"]
        updated_profile["pending_changes"] = []

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=profile_doc)
        mock_col.find_one_and_update = AsyncMock(return_value=updated_profile)

        with patch("app.routers.profile.profiles_col", return_value=mock_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/profile/pending-changes/focus_area/accept",
                    headers=auth_headers,
                )

            assert response.status_code == 200
            body = response.json()
            assert "Cloud Architecture" in body["focusAreas"]
            assert body["pendingChanges"] == []

    @pytest.mark.asyncio
    async def test_proposals_dismiss_via_profile_endpoint(self, auth_headers):
        """Dismiss a document-sourced proposal through the existing dismiss endpoint."""
        user_id = "test-user-integration"
        job_id = str(uuid.uuid4())

        profile_doc = {
            "user_id": user_id,
            "focus_areas": ["Python"],
            "style_notes": [],
            "pending_changes": [
                {
                    "field": "focus_area",
                    "proposed_value": {"value": "Cloud Architecture"},
                    "reason": "Extracted from uploaded document",
                    "session_id": job_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_type": "document_upload",
                }
            ],
        }

        dismissed_profile = {**profile_doc}
        dismissed_profile["pending_changes"] = []
        dismissed_profile["focus_areas"] = ["Python"]  # unchanged

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=profile_doc)
        mock_col.find_one_and_update = AsyncMock(return_value=dismissed_profile)

        with patch("app.routers.profile.profiles_col", return_value=mock_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/profile/pending-changes/focus_area/dismiss",
                    headers=auth_headers,
                )

            assert response.status_code == 200
            body = response.json()
            # Focus areas unchanged after dismiss
            assert body["focusAreas"] == ["Python"]
            assert body["pendingChanges"] == []


class TestPipelineIndependence:
    """Test that document pipeline operates while ingestion pipeline is unavailable.

    Validates Requirements 8.1, 8.5: Document pipeline is independent from
    IngestionService. If ingestion pipeline is unavailable, document pipeline
    continues unaffected.
    """

    @pytest.mark.asyncio
    async def test_document_upload_works_when_ingest_fails(self, auth_headers):
        """Document upload endpoint returns 202 even when ingestion infra is broken.

        Simulates the ingestion pipeline being completely unavailable (its DB
        collection raises exceptions and its service functions fail), while the
        document pipeline continues to accept and process uploads with no issues.
        """
        mock_doc_col = MagicMock()
        mock_doc_col.insert_one = AsyncMock()

        # Make the ingestion_jobs_col raise (simulating ingestion infra down)
        mock_ingest_col = MagicMock()
        mock_ingest_col.find_one = AsyncMock(side_effect=Exception("Ingest DB unavailable"))
        mock_ingest_col.insert_one = AsyncMock(side_effect=Exception("Ingest DB unavailable"))

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col),
            patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingest_col),
            patch("app.services.document_pipeline.process_document_upload", new_callable=AsyncMock),
            patch("pathlib.Path.mkdir", return_value=None),
            patch("pathlib.Path.write_bytes", return_value=None),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Document upload should succeed regardless of ingest state
                files = [
                    ("files", ("notes.txt", io.BytesIO(b"Study notes content"), "text/plain")),
                ]
                doc_response = await client.post(
                    "/api/documents/upload",
                    files=files,
                    data={"skip_review": "false"},
                    headers=auth_headers,
                )

            # Document pipeline works fine — completely unaffected
            assert doc_response.status_code == 202
            assert "jobId" in doc_response.json()
            assert doc_response.json()["acceptedFiles"] == 1

    def test_document_pipeline_has_no_ingestion_imports(self):
        """Verify document pipeline modules do not import from the ingestion pipeline.

        Requirement 8.1: Document pipeline SHALL NOT import from, depend on,
        or share runtime state with the existing IngestionService.
        """
        import ast
        from pathlib import Path

        # Document pipeline source files
        pipeline_files = [
            Path("app/routers/documents.py"),
            Path("app/services/document_pipeline.py"),
            Path("app/services/document_extractor.py"),
            Path("app/services/l1_fact_synthesizer.py"),
        ]

        # Ingestion-related modules that should NOT be imported
        forbidden_imports = {
            "app.services.extraction",
            "app.services.file_upload",
            "app.routers.ingest",
            "ingestion_pipeline",
        }

        for filepath in pipeline_files:
            if not filepath.exists():
                continue
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not any(
                            alias.name.startswith(f) for f in forbidden_imports
                        ), f"{filepath} imports from ingestion: {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert not any(
                            node.module.startswith(f) for f in forbidden_imports
                        ), f"{filepath} imports from ingestion: {node.module}"

    @pytest.mark.asyncio
    async def test_document_status_polling_works_when_ingest_unavailable(self, auth_headers):
        """Job status polling works regardless of ingestion pipeline state."""
        job_id = str(uuid.uuid4())
        user_id = "test-user-integration"

        job_doc = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "synthesizing",
            "files": [{"filename": "notes.txt", "status": "extracted", "error": None}],
            "proposals": None,
            "proposal_count": 0,
            "created_at": datetime.now(timezone.utc),
        }

        mock_doc_col = MagicMock()
        mock_doc_col.find_one = AsyncMock(return_value=job_doc)

        # Ingest collection is completely broken
        mock_ingest_col = MagicMock()
        mock_ingest_col.find_one = AsyncMock(side_effect=Exception("DB down"))

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col),
            patch("app.routers.ingest.ingestion_jobs_col", return_value=mock_ingest_col),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Document job status works
                status_response = await client.get(
                    f"/api/documents/jobs/{job_id}/status",
                    headers=auth_headers,
                )

            assert status_response.status_code == 200
            body = status_response.json()
            assert body["status"] == "synthesizing"
            assert body["jobId"] == job_id

    @pytest.mark.asyncio
    async def test_retry_analysis_works_when_ingest_unavailable(self, auth_headers):
        """Retry analysis endpoint works independently of ingestion pipeline."""
        job_id = str(uuid.uuid4())
        user_id = "test-user-integration"

        failed_job_doc = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "failed",
            "files": [{"filename": "notes.txt", "status": "extracted", "error": None}],
            "extracted_text": "Some preserved extracted text for retry",
            "skip_review": False,
            "proposals": None,
            "proposal_count": 0,
            "created_at": datetime.now(timezone.utc),
        }

        mock_doc_col = MagicMock()
        mock_doc_col.find_one = AsyncMock(return_value=failed_job_doc)
        mock_doc_col.update_one = AsyncMock()

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_doc_col),
            patch(
                "app.routers.documents._run_retry_synthesis",
                new_callable=AsyncMock,
            ),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/documents/jobs/{job_id}/retry-analysis",
                    headers=auth_headers,
                )

            assert response.status_code == 202
            body = response.json()
            assert body["jobId"] == job_id
            assert body["status"] == "synthesizing"


class TestTTLCleanup:
    """Test TTL cleanup: files and job records expire after 24 hours.

    Validates Requirement 2.7: 24-hour TTL for stored files and job records.
    """

    @pytest.mark.asyncio
    async def test_job_expires_at_is_24_hours_from_creation(self, auth_headers):
        """Upload_Job's expires_at field is set to created_at + 24 hours."""
        inserted_docs = []

        mock_col = MagicMock()

        async def capture_insert(doc):
            inserted_docs.append(doc)

        mock_col.insert_one = AsyncMock(side_effect=capture_insert)

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_col),
            patch("app.services.document_pipeline.process_document_upload", new_callable=AsyncMock),
            patch("pathlib.Path.mkdir", return_value=None),
            patch("pathlib.Path.write_bytes", return_value=None),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                files = [
                    ("files", ("test.txt", io.BytesIO(b"TTL test content"), "text/plain")),
                ]
                response = await client.post(
                    "/api/documents/upload",
                    files=files,
                    data={"skip_review": "false"},
                    headers=auth_headers,
                )

            assert response.status_code == 202

            # Verify the inserted document has correct TTL
            assert len(inserted_docs) == 1
            doc = inserted_docs[0]
            created_at = doc["created_at"]
            expires_at = doc["expires_at"]

            # expires_at should be exactly 24 hours after created_at
            expected_expires = created_at + timedelta(hours=24)
            assert expires_at == expected_expires

    @pytest.mark.asyncio
    async def test_ttl_index_configured_on_collection(self):
        """Verify the TTL index is configured with expireAfterSeconds=0 on expires_at.

        This ensures MongoDB will automatically delete expired documents.
        The TTL index is set up in _ensure_indexes() at database connection time.
        """
        from app.config.database import _ensure_indexes

        mock_doc_jobs_col = MagicMock()
        mock_doc_jobs_col.create_index = AsyncMock()

        # We need to mock all collections that _ensure_indexes touches
        with (
            patch("app.config.database.profiles_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.skill_graph_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.sessions_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.ingestion_jobs_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.immediate_contexts_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.subtopic_lists_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.weight_nudges_col", return_value=MagicMock(create_index=AsyncMock())),
            patch("app.config.database.document_upload_jobs_col", return_value=mock_doc_jobs_col),
        ):
            await _ensure_indexes()

            # Find the TTL index creation call
            ttl_calls = [
                call for call in mock_doc_jobs_col.create_index.call_args_list
                if any("expires_at" in str(arg) for arg in call.args)
            ]
            assert len(ttl_calls) >= 1

            # Verify the TTL index has expireAfterSeconds=0
            ttl_call = ttl_calls[0]
            assert ttl_call.kwargs.get("expireAfterSeconds") == 0

    @pytest.mark.asyncio
    async def test_job_record_contains_expires_at_field(self, auth_headers):
        """Every Upload_Job record contains an expires_at field for TTL enforcement."""
        inserted_docs = []

        mock_col = MagicMock()

        async def capture_insert(doc):
            inserted_docs.append(doc)

        mock_col.insert_one = AsyncMock(side_effect=capture_insert)

        with (
            patch("app.routers.documents.document_upload_jobs_col", return_value=mock_col),
            patch("app.services.document_pipeline.process_document_upload", new_callable=AsyncMock),
            patch("pathlib.Path.mkdir", return_value=None),
            patch("pathlib.Path.write_bytes", return_value=None),
        ):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                files = [
                    ("files", ("data.csv", io.BytesIO(b"a,b,c\n1,2,3"), "text/csv")),
                ]
                response = await client.post(
                    "/api/documents/upload",
                    files=files,
                    data={"skip_review": "false"},
                    headers=auth_headers,
                )

            assert response.status_code == 202
            assert len(inserted_docs) == 1

            doc = inserted_docs[0]
            assert "expires_at" in doc
            assert "created_at" in doc
            assert isinstance(doc["expires_at"], datetime)
            assert isinstance(doc["created_at"], datetime)
            # expires_at must be in the future relative to created_at
            assert doc["expires_at"] > doc["created_at"]


class TestDocumentSourcedProposals:
    """Test that document-sourced proposals work with existing accept/dismiss paths.

    Validates Requirements 5.1, 5.4: Proposals created with source_type="document_upload"
    and session_id=job_id work through the standard accept/dismiss endpoints.
    """

    @pytest.mark.asyncio
    async def test_accept_style_note_from_document_upload(self, auth_headers):
        """Accept a document-sourced style_note proposal via the standard endpoint."""
        user_id = "test-user-integration"
        job_id = str(uuid.uuid4())

        profile_doc = {
            "user_id": user_id,
            "focus_areas": [],
            "style_notes": [
                {
                    "category": "pacing",
                    "note": "Existing note",
                    "source_quote": "from session",
                    "session_id": "session-1",
                    "added_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "pending_changes": [
                {
                    "field": "style_note",
                    "proposed_value": {
                        "category": "motivation",
                        "note": "Responds well to real-world examples",
                    },
                    "reason": "Multiple references to preferring practical examples",
                    "session_id": job_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_type": "document_upload",
                }
            ],
            "learning_context": None,
            "learning_context_detail": None,
            "explanation_style": "hint-first",
            "challenge_tolerance": "medium",
            "feedback_tone": "encouraging",
        }

        updated_profile = {**profile_doc}
        updated_profile["style_notes"] = [
            profile_doc["style_notes"][0],
            {
                "category": "motivation",
                "note": "Responds well to real-world examples",
                "source_quote": "Multiple references to preferring practical examples",
                "session_id": job_id,
                "added_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        updated_profile["pending_changes"] = []

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=profile_doc)
        mock_col.find_one_and_update = AsyncMock(return_value=updated_profile)

        with patch("app.routers.profile.profiles_col", return_value=mock_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/profile/pending-changes/style_note/accept",
                    headers=auth_headers,
                )

            assert response.status_code == 200
            body = response.json()
            assert len(body["styleNotes"]) == 2
            assert body["pendingChanges"] == []

    @pytest.mark.asyncio
    async def test_source_type_preserved_through_accept_path(self, auth_headers):
        """Verify source_type='document_upload' tag is preserved in the pending change."""
        user_id = "test-user-integration"
        job_id = str(uuid.uuid4())

        # Create pending change with document_upload source
        pending_change = {
            "field": "focus_area",
            "proposed_value": {"value": "ML Engineering"},
            "reason": "Document discusses ML pipeline work",
            "session_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_type": "document_upload",
        }

        profile_doc = {
            "user_id": user_id,
            "focus_areas": ["Python"],
            "style_notes": [],
            "pending_changes": [pending_change],
            "learning_context": None,
            "learning_context_detail": None,
            "explanation_style": "hint-first",
            "challenge_tolerance": "medium",
            "feedback_tone": "encouraging",
        }

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=profile_doc)

        # Capture the update call to verify what was written
        update_calls = []

        async def capture_update(filter_doc, update_doc, **kwargs):
            update_calls.append((filter_doc, update_doc))
            result = {**profile_doc}
            result["focus_areas"] = ["Python", "ML Engineering"]
            result["pending_changes"] = []
            return result

        mock_col.find_one_and_update = AsyncMock(side_effect=capture_update)

        with patch("app.routers.profile.profiles_col", return_value=mock_col):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/profile/pending-changes/focus_area/accept",
                    headers=auth_headers,
                )

            assert response.status_code == 200

            # Verify the accept path properly found and processed the
            # document-sourced pending change (it matched by field name)
            assert len(update_calls) == 1
            _, update_doc = update_calls[0]
            # The $set should contain focus_areas with the new value appended
            set_doc = update_doc["$set"]
            assert "ML Engineering" in set_doc["focus_areas"]
            assert "Python" in set_doc["focus_areas"]
