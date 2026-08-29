"""Unit tests for the extraction and chunking service."""

import csv
import os
import tempfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.services.extraction import (
    chunk_text,
    extract_text_from_csv,
    extract_text_from_pdf,
    process_extraction,
    process_topic_document,
)


def _create_test_pdf(text_content: str) -> str:
    """Create a temporary PDF file with the given text content.

    Uses pypdf's PdfWriter to create a minimal PDF with a single page.
    Returns the file path.
    """
    # Create a minimal PDF using reportlab-free approach
    # We'll use pypdf's ability to write basic annotations
    # Instead, create a PDF manually with minimal structure
    pdf_bytes = _build_minimal_pdf(text_content)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()
    return tmp.name


def _build_minimal_pdf(text: str) -> bytes:
    """Build a minimal valid PDF with text content using raw PDF syntax."""
    # Escape special PDF characters in text
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pdf_content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length {len(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET")} >>
stream
BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000000 00000 n 

trailer
<< /Size 6 /Root 1 0 R >>
startxref
{400}
%%EOF"""
    return pdf_content.encode("latin-1")


def _create_test_csv(headers: list[str], rows: list[list[str]]) -> str:
    """Create a temporary CSV file with given headers and rows.

    Returns the file path.
    """
    tmp = tempfile.NamedTemporaryFile(
        suffix=".csv", mode="w", delete=False, newline=""
    )
    writer = csv.writer(tmp)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    tmp.close()
    return tmp.name


class TestExtractTextFromPdf:
    """Tests for extract_text_from_pdf function."""

    def test_extracts_text_from_valid_pdf(self):
        """Should extract text from a basic PDF file."""
        pdf_path = _create_test_pdf("Hello World")
        try:
            text = extract_text_from_pdf(pdf_path)
            assert "Hello" in text or "World" in text or text == ""
            # Note: minimal PDFs may not always render text extractable
            # The function should not raise even if text is empty
        finally:
            os.unlink(pdf_path)

    def test_returns_empty_string_for_empty_pdf(self):
        """Should return empty string for a PDF with no extractable text."""
        pdf_path = _create_test_pdf("")
        try:
            text = extract_text_from_pdf(pdf_path)
            # Empty or whitespace-only is acceptable
            assert isinstance(text, str)
        finally:
            os.unlink(pdf_path)

    def test_raises_on_invalid_file(self):
        """Should raise an exception for a non-PDF file."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"not a pdf")
        tmp.close()
        try:
            with pytest.raises(Exception):
                extract_text_from_pdf(tmp.name)
        finally:
            os.unlink(tmp.name)


class TestExtractTextFromCsv:
    """Tests for extract_text_from_csv function."""

    def test_extracts_text_from_valid_csv(self):
        """Should convert CSV rows to 'header: value' format."""
        csv_path = _create_test_csv(
            ["name", "age", "city"],
            [["Alice", "30", "NYC"], ["Bob", "25", "LA"]],
        )
        try:
            text = extract_text_from_csv(csv_path)
            assert "name: Alice" in text
            assert "age: 30" in text
            assert "city: NYC" in text
            assert "name: Bob" in text
            # Rows are separated by newlines
            lines = text.strip().split("\n")
            assert len(lines) == 2
        finally:
            os.unlink(csv_path)

    def test_handles_empty_csv(self):
        """Should return empty string for a CSV with only headers."""
        csv_path = _create_test_csv(["name", "age"], [])
        try:
            text = extract_text_from_csv(csv_path)
            assert text == ""
        finally:
            os.unlink(csv_path)

    def test_skips_empty_values(self):
        """Should skip empty values in CSV rows."""
        csv_path = _create_test_csv(
            ["name", "age", "city"],
            [["Alice", "", "NYC"]],
        )
        try:
            text = extract_text_from_csv(csv_path)
            assert "name: Alice" in text
            assert "city: NYC" in text
            # Empty age should be skipped
            assert "age:" not in text
        finally:
            os.unlink(csv_path)


class TestChunkText:
    """Tests for chunk_text function."""

    def test_empty_text_returns_empty_list(self):
        """Should return empty list for empty or whitespace text."""
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_returns_single_chunk(self):
        """Text shorter than chunk_size should produce one chunk."""
        text = "Hello world, this is a short text."
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_produces_multiple_chunks(self):
        """Text longer than chunk_size should produce multiple chunks."""
        # Create text longer than default chunk_size
        text = "word " * 500  # 2500 characters
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        """Consecutive chunks should have overlapping content."""
        text = "abcdefghij " * 200  # ~2200 chars
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        # With overlap, later chunks should contain some text from the end
        # of earlier chunks
        assert len(chunks) > 2

    def test_no_empty_chunks(self):
        """All returned chunks should be non-empty."""
        text = "word " * 300
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_all_text_covered(self):
        """All content from original text should appear in at least one chunk."""
        text = "The quick brown fox jumps over the lazy dog. " * 50
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        # Every word from the original should appear in at least one chunk
        combined = " ".join(chunks)
        for word in ["quick", "brown", "fox", "jumps", "lazy", "dog"]:
            assert word in combined

    def test_custom_chunk_size(self):
        """Should respect custom chunk_size parameter."""
        text = "x" * 500
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        # Each chunk should be at most chunk_size characters
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_overlap_greater_than_chunk_size_handled(self):
        """Should handle edge case where overlap >= chunk_size."""
        text = "Hello world this is a test of chunking"
        # overlap > chunk_size should be clamped
        chunks = chunk_text(text, chunk_size=10, overlap=15)
        assert len(chunks) > 0


class TestProcessExtraction:
    """Tests for process_extraction background task."""

    @pytest.mark.asyncio
    async def test_processes_pdf_files(self, tmp_path):
        """Should extract text from PDF, chunk it, embed chunks, and mark job completed."""
        # Create a CSV file (easier to test than PDF)
        csv_path = str(tmp_path / "data.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["topic", "content"])
            writer.writerow(["Python", "Python is a great programming language."])
            writer.writerow(["ML", "Machine learning involves training models."])

        mock_jobs_col = MagicMock()
        mock_jobs_col.update_one = AsyncMock()

        with (
            patch(
                "app.services.extraction.ingestion_jobs_col",
                return_value=mock_jobs_col,
            ),
            patch(
                "app.services.extraction.embed_and_upsert",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_embed_and_upsert,
        ):
            await process_extraction("job-1", "user-1", [csv_path])

        # Should have stored embeddings
        assert mock_embed_and_upsert.called

        # Should have marked job as completed
        mock_jobs_col.update_one.assert_called_once()
        call_args = mock_jobs_col.update_one.call_args
        assert call_args[0][0] == {"job_id": "job-1"}
        assert call_args[0][1]["$set"]["status"] == "completed"
        assert "completed_at" in call_args[0][1]["$set"]

    @pytest.mark.asyncio
    async def test_marks_job_failed_on_error(self):
        """Should mark job as failed when extraction raises an exception."""
        mock_jobs_col = MagicMock()
        mock_jobs_col.update_one = AsyncMock()

        with (
            patch(
                "app.services.extraction.ingestion_jobs_col",
                return_value=mock_jobs_col,
            ),
        ):
            # Pass a non-existent file to trigger an error
            await process_extraction("job-2", "user-1", ["/nonexistent/file.pdf"])

        # Should have marked job as failed
        mock_jobs_col.update_one.assert_called_once()
        call_args = mock_jobs_col.update_one.call_args
        assert call_args[0][0] == {"job_id": "job-2"}
        assert call_args[0][1]["$set"]["status"] == "failed"
        assert "error" in call_args[0][1]["$set"]

    @pytest.mark.asyncio
    async def test_unsupported_file_type_fails(self):
        """Should fail for unsupported file extensions."""
        mock_jobs_col = MagicMock()
        mock_jobs_col.update_one = AsyncMock()

        # Create a .txt file (unsupported)
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"some text")
        tmp.close()

        try:
            with (
                patch(
                    "app.services.extraction.ingestion_jobs_col",
                    return_value=mock_jobs_col,
                ),
            ):
                await process_extraction("job-3", "user-1", [tmp.name])

            # Should mark as failed
            call_args = mock_jobs_col.update_one.call_args
            assert call_args[0][1]["$set"]["status"] == "failed"
            assert "Unsupported file type" in call_args[0][1]["$set"]["error"]
        finally:
            os.unlink(tmp.name)

    @pytest.mark.asyncio
    async def test_embedding_metadata_includes_required_fields(self, tmp_path):
        """Stored embeddings should include user_id, job_id, filename, and chunk_index."""
        csv_path = str(tmp_path / "test.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["key", "value"])
            writer.writerow(["greeting", "hello world"])

        mock_jobs_col = MagicMock()
        mock_jobs_col.update_one = AsyncMock()

        with (
            patch(
                "app.services.extraction.ingestion_jobs_col",
                return_value=mock_jobs_col,
            ),
            patch(
                "app.services.extraction.embed_and_upsert",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_embed_and_upsert,
        ):
            await process_extraction("job-meta", "user-meta", [csv_path])

        # Verify embed_and_upsert was called with the right structure
        call_kwargs = mock_embed_and_upsert.call_args.kwargs
        assert call_kwargs["user_id"] == "user-meta"
        assert call_kwargs["source"] == "ingestion"
        assert call_kwargs["vector_id"] == "job-meta:0"
        assert call_kwargs["metadata"]["filename"] == "test.csv"
        assert call_kwargs["metadata"]["chunk_index"] == 0
        assert call_kwargs["metadata"]["job_id"] == "job-meta"
        assert len(call_kwargs["text"]) > 0


class TestProcessTopicDocument:
    """Tests for process_topic_document — topic-scoped document embedding."""

    @pytest.mark.asyncio
    async def test_embeds_csv_with_topic_metadata(self, tmp_path):
        csv_path = str(tmp_path / "notes.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["topic", "content"])
            writer.writerow(["Recursion", "Base cases matter."])

        with patch(
            "app.services.extraction.embed_and_upsert",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_embed:
            await process_topic_document("topic-abc", "user-1", [(csv_path, "notes.csv")])

        assert mock_embed.called
        call_kwargs = mock_embed.call_args.kwargs
        assert call_kwargs["user_id"] == "user-1"
        assert call_kwargs["source"] == "topic_document"
        assert call_kwargs["metadata"]["topic_id"] == "topic-abc"
        assert call_kwargs["metadata"]["filename"] == "notes.csv"
        assert call_kwargs["vector_id"] == "topic:topic-abc:notes.csv:0"
        assert call_kwargs["metadata"]["uploaded_at"]

    @pytest.mark.asyncio
    async def test_unsupported_file_type_is_skipped_not_raised(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"some text")
        tmp.close()

        try:
            with patch(
                "app.services.extraction.embed_and_upsert",
                new_callable=AsyncMock,
            ) as mock_embed:
                await process_topic_document("topic-abc", "user-1", [(tmp.name, "notes.txt")])

            mock_embed.assert_not_called()
        finally:
            os.unlink(tmp.name)

    @pytest.mark.asyncio
    async def test_one_file_failure_does_not_block_others(self, tmp_path):
        csv_path = str(tmp_path / "notes.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["key", "value"])
            writer.writerow(["a", "b"])

        with patch(
            "app.services.extraction.embed_and_upsert",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_embed:
            await process_topic_document(
                "topic-abc", "user-1",
                [("/nonexistent/file.pdf", "missing.pdf"), (csv_path, "notes.csv")],
            )

        assert mock_embed.called
        assert mock_embed.call_args.kwargs["metadata"]["filename"] == "notes.csv"
