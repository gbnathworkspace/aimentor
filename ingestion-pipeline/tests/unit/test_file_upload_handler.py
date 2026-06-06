"""Unit tests for FileUploadHandler validation and S3 upload logic."""

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError

from app.models.schemas import IngestionFile, IngestionJobResponse, IngestionStatus
from app.services.file_upload_handler import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    MAX_FILES,
    FileUploadHandler,
    S3UploadError,
    construct_s3_key,
)

pytestmark = pytest.mark.asyncio


def _make_upload_file(content: bytes, filename: str, content_type: str):
    """Create a mock UploadFile for testing."""
    mock = AsyncMock()
    mock.filename = filename
    mock.content_type = content_type
    mock.read = AsyncMock(return_value=content)
    return mock


@pytest.fixture
def handler():
    return FileUploadHandler()


@pytest.mark.asyncio
async def test_valid_pdf_upload(handler):
    """A valid PDF file should pass validation."""
    files = [_make_upload_file(b"PDF content here", "resume.pdf", "application/pdf")]
    errors, validated = await handler.handle_upload("user123", files)
    assert errors is None
    assert validated is not None
    assert len(validated) == 1
    assert validated[0] == (b"PDF content here", "resume.pdf", "application/pdf")


@pytest.mark.asyncio
async def test_valid_csv_upload(handler):
    """A valid CSV file should pass validation."""
    files = [_make_upload_file(b"col1,col2\nval1,val2", "data.csv", "text/csv")]
    errors, validated = await handler.handle_upload("user123", files)
    assert errors is None
    assert validated is not None
    assert len(validated) == 1
    assert validated[0][1] == "data.csv"
    assert validated[0][2] == "text/csv"


@pytest.mark.asyncio
async def test_valid_two_files(handler):
    """Two valid files should pass validation."""
    files = [
        _make_upload_file(b"PDF content", "resume.pdf", "application/pdf"),
        _make_upload_file(b"csv,data\n1,2", "leetcode.csv", "text/csv"),
    ]
    errors, validated = await handler.handle_upload("user123", files)
    assert errors is None
    assert validated is not None
    assert len(validated) == 2


@pytest.mark.asyncio
async def test_too_many_files(handler):
    """More than 2 files should fail with file count error."""
    files = [
        _make_upload_file(b"a", "f1.pdf", "application/pdf"),
        _make_upload_file(b"b", "f2.pdf", "application/pdf"),
        _make_upload_file(b"c", "f3.pdf", "application/pdf"),
    ]
    errors, validated = await handler.handle_upload("user123", files)
    assert validated is None
    assert errors is not None
    assert len(errors) == 1
    assert errors[0].field == "files"
    assert "Maximum" in errors[0].message


@pytest.mark.asyncio
async def test_invalid_mime_type(handler):
    """An unsupported MIME type should fail validation."""
    files = [_make_upload_file(b"content", "image.png", "image/png")]
    errors, validated = await handler.handle_upload("user123", files)
    assert validated is None
    assert errors is not None
    assert len(errors) == 1
    assert errors[0].field == "file"
    assert errors[0].supported_types == ["application/pdf", "text/csv"]


@pytest.mark.asyncio
async def test_empty_file(handler):
    """A zero-byte file should fail validation."""
    files = [_make_upload_file(b"", "empty.pdf", "application/pdf")]
    errors, validated = await handler.handle_upload("user123", files)
    assert validated is None
    assert errors is not None
    assert len(errors) == 1
    assert errors[0].field == "file"
    assert errors[0].max_size_mb == 10


@pytest.mark.asyncio
async def test_oversized_file(handler):
    """A file exceeding 10MB should fail validation."""
    large_content = b"x" * (MAX_FILE_SIZE + 1)
    files = [_make_upload_file(large_content, "big.pdf", "application/pdf")]
    errors, validated = await handler.handle_upload("user123", files)
    assert validated is None
    assert errors is not None
    assert len(errors) == 1
    assert errors[0].max_size_mb == 10


@pytest.mark.asyncio
async def test_mixed_valid_and_invalid(handler):
    """If one file is invalid, entire upload should return errors."""
    files = [
        _make_upload_file(b"good content", "resume.pdf", "application/pdf"),
        _make_upload_file(b"bad", "file.exe", "application/octet-stream"),
    ]
    errors, validated = await handler.handle_upload("user123", files)
    assert validated is None
    assert errors is not None
    assert len(errors) == 1
    assert errors[0].supported_types is not None


# --- Tests for construct_s3_key ---


class TestConstructS3Key:
    """Tests for the module-level construct_s3_key helper."""

    def test_basic_key_construction(self):
        """Key should follow uploads/{user_id}/{job_id}/{filename} format."""
        key = construct_s3_key("user123", "job-abc", "resume.pdf")
        assert key == "uploads/user123/job-abc/resume.pdf"

    def test_preserves_special_characters_in_filename(self):
        """Filename with spaces or special characters is preserved as-is."""
        key = construct_s3_key("u1", "j1", "my resume (1).pdf")
        assert key == "uploads/u1/j1/my resume (1).pdf"

    def test_empty_components(self):
        """Even empty strings produce the correct structure."""
        key = construct_s3_key("", "", "")
        assert key == "uploads///"


# --- Tests for upload_to_s3 ---


class TestUploadToS3:
    """Tests for FileUploadHandler.upload_to_s3."""

    @patch("app.services.file_upload_handler.get_settings")
    @patch("app.services.file_upload_handler.get_s3_client")
    def test_successful_upload_returns_job_id_and_files(self, mock_get_s3, mock_get_settings):
        """Successful S3 upload returns a UUID job_id and IngestionFile list."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_get_settings.return_value = MagicMock(S3_BUCKET="test-bucket")

        handler = FileUploadHandler()
        validated_files = [
            (b"pdf content", "resume.pdf", "application/pdf"),
            (b"csv,data\n1,2", "leetcode.csv", "text/csv"),
        ]

        job_id, ingestion_files = handler.upload_to_s3("user123", validated_files)

        # job_id should be a valid UUID4 string
        parsed = uuid.UUID(job_id, version=4)
        assert str(parsed) == job_id

        # Should return correct number of IngestionFile objects
        assert len(ingestion_files) == 2

        # Verify first file metadata
        assert ingestion_files[0].filename == "resume.pdf"
        assert ingestion_files[0].mime_type == "application/pdf"
        assert ingestion_files[0].size_bytes == len(b"pdf content")
        assert ingestion_files[0].s3_key == f"uploads/user123/{job_id}/resume.pdf"

        # Verify second file metadata
        assert ingestion_files[1].filename == "leetcode.csv"
        assert ingestion_files[1].mime_type == "text/csv"
        assert ingestion_files[1].size_bytes == len(b"csv,data\n1,2")
        assert ingestion_files[1].s3_key == f"uploads/user123/{job_id}/leetcode.csv"

    @patch("app.services.file_upload_handler.get_settings")
    @patch("app.services.file_upload_handler.get_s3_client")
    def test_s3_put_object_called_correctly(self, mock_get_s3, mock_get_settings):
        """S3 put_object should be called with correct parameters for each file."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_get_settings.return_value = MagicMock(S3_BUCKET="my-bucket")

        handler = FileUploadHandler()
        validated_files = [(b"file data", "test.pdf", "application/pdf")]

        job_id, _ = handler.upload_to_s3("user456", validated_files)

        mock_s3.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key=f"uploads/user456/{job_id}/test.pdf",
            Body=b"file data",
            ContentType="application/pdf",
        )

    @patch("app.services.file_upload_handler.get_settings")
    @patch("app.services.file_upload_handler.get_s3_client")
    def test_s3_failure_raises_s3_upload_error(self, mock_get_s3, mock_get_settings):
        """A ClientError from S3 should be wrapped in S3UploadError."""
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "S3 is down"}},
            "PutObject",
        )
        mock_get_s3.return_value = mock_s3
        mock_get_settings.return_value = MagicMock(S3_BUCKET="test-bucket")

        handler = FileUploadHandler()
        validated_files = [(b"data", "file.pdf", "application/pdf")]

        with pytest.raises(S3UploadError) as exc_info:
            handler.upload_to_s3("user123", validated_files)

        assert "Failed to upload file to S3" in str(exc_info.value)

    @patch("app.services.file_upload_handler.get_settings")
    @patch("app.services.file_upload_handler.get_s3_client")
    def test_s3_failure_does_not_return_partial_results(self, mock_get_s3, mock_get_settings):
        """If S3 fails on the second file, no job record should be created."""
        mock_s3 = MagicMock()
        # First call succeeds, second call fails
        mock_s3.put_object.side_effect = [
            None,
            ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "No access"}},
                "PutObject",
            ),
        ]
        mock_get_s3.return_value = mock_s3
        mock_get_settings.return_value = MagicMock(S3_BUCKET="test-bucket")

        handler = FileUploadHandler()
        validated_files = [
            (b"first", "a.pdf", "application/pdf"),
            (b"second", "b.csv", "text/csv"),
        ]

        with pytest.raises(S3UploadError):
            handler.upload_to_s3("user123", validated_files)

    @patch("app.services.file_upload_handler.get_settings")
    @patch("app.services.file_upload_handler.get_s3_client")
    def test_each_call_generates_unique_job_id(self, mock_get_s3, mock_get_settings):
        """Each upload_to_s3 call should generate a different job_id."""
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_get_settings.return_value = MagicMock(S3_BUCKET="test-bucket")

        handler = FileUploadHandler()
        validated_files = [(b"data", "file.pdf", "application/pdf")]

        job_id_1, _ = handler.upload_to_s3("user1", validated_files)
        job_id_2, _ = handler.upload_to_s3("user1", validated_files)

        assert job_id_1 != job_id_2


# --- Tests for create_job_and_enqueue ---


class TestCreateJobAndEnqueue:
    """Tests for FileUploadHandler.create_job_and_enqueue."""

    @pytest.mark.asyncio
    @patch("app.services.file_upload_handler.get_ingestion_jobs_collection")
    async def test_creates_job_record_with_pending_status(self, mock_get_collection):
        """Should insert a JobRecord with status='pending' into MongoDB."""
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock()
        mock_get_collection.return_value = mock_collection

        handler = FileUploadHandler()
        background_tasks = MagicMock()
        ingestion_files = [
            IngestionFile(
                filename="resume.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                s3_key="uploads/user1/job1/resume.pdf",
            )
        ]

        result = await handler.create_job_and_enqueue(
            job_id="job-123",
            user_id="user-abc",
            ingestion_files=ingestion_files,
            background_tasks=background_tasks,
        )

        # Verify insert_one was called
        mock_collection.insert_one.assert_called_once()
        inserted_doc = mock_collection.insert_one.call_args[0][0]

        assert inserted_doc["job_id"] == "job-123"
        assert inserted_doc["user_id"] == "user-abc"
        assert inserted_doc["status"] == IngestionStatus.pending
        assert len(inserted_doc["files"]) == 1
        assert inserted_doc["files"][0]["filename"] == "resume.pdf"
        assert inserted_doc["created_at"] is not None
        assert inserted_doc["updated_at"] is not None

    @pytest.mark.asyncio
    @patch("app.services.file_upload_handler.get_ingestion_jobs_collection")
    async def test_returns_ingestion_job_response(self, mock_get_collection):
        """Should return an IngestionJobResponse with the correct job_id."""
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock()
        mock_get_collection.return_value = mock_collection

        handler = FileUploadHandler()
        background_tasks = MagicMock()

        result = await handler.create_job_and_enqueue(
            job_id="my-job-id",
            user_id="user1",
            ingestion_files=[],
            background_tasks=background_tasks,
        )

        assert isinstance(result, IngestionJobResponse)
        assert result.job_id == "my-job-id"

    @pytest.mark.asyncio
    @patch("app.services.file_upload_handler.get_ingestion_jobs_collection")
    async def test_enqueues_background_task(self, mock_get_collection):
        """Should enqueue _run_extraction as a background task."""
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock()
        mock_get_collection.return_value = mock_collection

        handler = FileUploadHandler()
        background_tasks = MagicMock()

        await handler.create_job_and_enqueue(
            job_id="job-456",
            user_id="user1",
            ingestion_files=[],
            background_tasks=background_tasks,
        )

        background_tasks.add_task.assert_called_once_with(
            handler._run_extraction, "job-456"
        )

    @pytest.mark.asyncio
    @patch("app.services.file_upload_handler.get_ingestion_jobs_collection")
    async def test_job_record_has_default_fields(self, mock_get_collection):
        """JobRecord should have default values for optional fields."""
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock()
        mock_get_collection.return_value = mock_collection

        handler = FileUploadHandler()
        background_tasks = MagicMock()

        await handler.create_job_and_enqueue(
            job_id="job-789",
            user_id="user2",
            ingestion_files=[],
            background_tasks=background_tasks,
        )

        inserted_doc = mock_collection.insert_one.call_args[0][0]
        assert inserted_doc["error"] is None
        assert inserted_doc["structured_done"] is False
        assert inserted_doc["embedding_done"] is False
        assert inserted_doc["source_category"] is None
        assert inserted_doc["completed_at"] is None
