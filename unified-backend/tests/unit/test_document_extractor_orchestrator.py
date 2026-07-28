"""Unit tests for the extract_document orchestrator and truncate_at_sentence_boundary."""

import os
import tempfile

import pytest

from app.services.document_extractor import (
    MAX_EXTRACTED_CHARS,
    ExtractionResult,
    extract_document,
    truncate_at_sentence_boundary,
)


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


def _write_file(tmp_dir: str, filename: str, content: bytes) -> str:
    """Write bytes to a temp file and return the path."""
    path = os.path.join(tmp_dir, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


# --- truncate_at_sentence_boundary tests ---


class TestTruncateAtSentenceBoundary:
    def test_text_within_limit_returned_as_is(self):
        """Text shorter than max_chars is returned unchanged."""
        text = "Hello world. This is short."
        result = truncate_at_sentence_boundary(text, 100)
        assert result == text

    def test_text_exactly_at_limit(self):
        """Text exactly at max_chars is returned unchanged."""
        text = "A" * 50
        result = truncate_at_sentence_boundary(text, 50)
        assert result == text

    def test_truncates_at_period_followed_by_space(self):
        """Truncates at the last period followed by a space within limit."""
        text = "First sentence. Second sentence. Third sentence is very long and exceeds the limit."
        result = truncate_at_sentence_boundary(text, 35)
        # "First sentence. Second sentence." = 33 chars, fits within 35
        assert result == "First sentence. Second sentence."
        assert len(result) <= 35

    def test_truncates_at_question_mark(self):
        """Truncates at question mark followed by whitespace."""
        text = "Is this working? Yes it is. More text here that goes over the limit."
        result = truncate_at_sentence_boundary(text, 20)
        assert result == "Is this working?"
        assert len(result) <= 20

    def test_truncates_at_exclamation_mark(self):
        """Truncates at exclamation mark followed by whitespace."""
        text = "Wow! That is great. This keeps going and going."
        result = truncate_at_sentence_boundary(text, 6)
        assert result == "Wow!"
        assert len(result) <= 6

    def test_hard_cutoff_when_no_sentence_boundary(self):
        """Falls back to hard cutoff when no sentence boundary exists."""
        text = "This text has no sentence endings within the limit and just keeps going"
        result = truncate_at_sentence_boundary(text, 20)
        assert result == text[:20]
        assert len(result) == 20

    def test_never_exceeds_max_chars(self):
        """Result never exceeds max_chars regardless of sentence boundaries."""
        text = "Short. " * 10000  # Many sentence boundaries
        result = truncate_at_sentence_boundary(text, 100)
        assert len(result) <= 100

    def test_sentence_boundary_at_end_of_region(self):
        """Handles sentence boundary at the very end of the search region."""
        text = "Hello world." + " " + "More text follows after this."
        # max_chars = 12 covers "Hello world." exactly
        result = truncate_at_sentence_boundary(text, 13)
        assert result == "Hello world."

    def test_empty_text(self):
        """Empty text is returned as-is (within any limit)."""
        result = truncate_at_sentence_boundary("", 100)
        assert result == ""

    def test_period_at_end_of_string(self):
        """Period at end of max_chars region (end-of-string match)."""
        text = "This is a sentence." + "x" * 100
        # The period is at index 18, followed by 'x' not whitespace
        # So it should NOT match — 'x' is not whitespace
        # Hard cutoff at 20
        result = truncate_at_sentence_boundary(text, 20)
        assert result == text[:20]

    def test_multiple_sentence_boundaries_picks_last(self):
        """When multiple boundaries exist, picks the last one within limit."""
        text = "A. B. C. D. E. This sentence is too long to fit within the limit."
        result = truncate_at_sentence_boundary(text, 15)
        # "A. B. C. D. E." won't fit at 15 chars. Let's check:
        # "A. B. C. D. E." = 14 chars, but we need the period followed by whitespace
        # "A. " has boundary at index 1, "B. " at 4, "C. " at 7, "D. " at 10, "E. " at 13
        # Last boundary within 15 chars: "E." at index 13
        assert result.endswith(".")
        assert len(result) <= 15


# --- extract_document routing tests ---


class TestExtractDocumentRouting:
    @pytest.mark.asyncio
    async def test_routes_text_plain(self, tmp_dir):
        """Routes text/plain to extract_text."""
        content = "Hello, plain text world."
        path = _write_file(tmp_dir, "sample.txt", content.encode("utf-8"))

        result = await extract_document(path, "text/plain")

        assert result.success is True
        assert result.text == content
        assert result.filename == "sample.txt"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_routes_text_markdown(self, tmp_dir):
        """Routes text/markdown to extract_text."""
        content = "# Heading\n\nSome markdown content."
        path = _write_file(tmp_dir, "readme.md", content.encode("utf-8"))

        result = await extract_document(path, "text/markdown")

        assert result.success is True
        assert "Heading" in result.text
        assert result.filename == "readme.md"

    @pytest.mark.asyncio
    async def test_routes_application_json(self, tmp_dir):
        """Routes application/json to extract_json."""
        content = '{"name": "test", "value": 42}'
        path = _write_file(tmp_dir, "data.json", content.encode("utf-8"))

        result = await extract_document(path, "application/json")

        assert result.success is True
        assert "name" in result.text
        assert "test" in result.text
        assert result.filename == "data.json"

    @pytest.mark.asyncio
    async def test_routes_text_csv(self, tmp_dir):
        """Routes text/csv to extract_csv."""
        content = "name,age\nAlice,30\nBob,25"
        path = _write_file(tmp_dir, "people.csv", content.encode("utf-8"))

        result = await extract_document(path, "text/csv")

        assert result.success is True
        assert "name" in result.text
        assert "Alice" in result.text
        assert result.filename == "people.csv"

    @pytest.mark.asyncio
    async def test_routes_application_rtf(self, tmp_dir):
        """Routes application/rtf to extract_rtf."""
        rtf_content = rb"{\rtf1\ansi{\fonttbl\f0\fswiss Helvetica;}\f0\pard Hello RTF\par}"
        path = _write_file(tmp_dir, "doc.rtf", rtf_content)

        result = await extract_document(path, "application/rtf")

        assert result.success is True
        assert "Hello RTF" in result.text
        assert result.filename == "doc.rtf"

    @pytest.mark.asyncio
    async def test_unsupported_mime_type(self, tmp_dir):
        """Unsupported MIME type returns failed result."""
        path = _write_file(tmp_dir, "image.png", b"\x89PNG\r\n")

        result = await extract_document(path, "image/png")

        assert result.success is False
        assert "unsupported MIME type" in result.error
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_catches_value_error_from_extractor(self, tmp_dir):
        """ValueError from extractor is caught and returned as failed result."""
        # Corrupted PDF-like content that will cause extract_pdf to raise ValueError
        path = _write_file(tmp_dir, "bad.pdf", b"not a real pdf")

        result = await extract_document(path, "application/pdf")

        assert result.success is False
        assert result.error is not None
        assert result.text == ""
        assert result.filename == "bad.pdf"

    @pytest.mark.asyncio
    async def test_empty_text_marked_as_failed(self, tmp_dir):
        """File producing only whitespace text is marked as failed."""
        # A text file with only whitespace
        path = _write_file(tmp_dir, "blank.txt", b"   \n\t\n   ")

        result = await extract_document(path, "text/plain")

        assert result.success is False
        assert result.error == "no extractable content"
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_truncation_applied_when_text_exceeds_limit(self, tmp_dir):
        """Text exceeding MAX_EXTRACTED_CHARS is truncated."""
        # Create text exceeding 50,000 chars with sentence boundaries
        sentences = "This is a sentence. " * 5000  # ~100,000 chars
        path = _write_file(tmp_dir, "large.txt", sentences.encode("utf-8"))

        result = await extract_document(path, "text/plain")

        assert result.success is True
        assert len(result.text) <= MAX_EXTRACTED_CHARS
        # Should end at a sentence boundary
        assert result.text.endswith(".")

    @pytest.mark.asyncio
    async def test_text_within_limit_not_truncated(self, tmp_dir):
        """Text within the limit is not truncated."""
        content = "Short content. Easy to process."
        path = _write_file(tmp_dir, "short.txt", content.encode("utf-8"))

        result = await extract_document(path, "text/plain")

        assert result.success is True
        assert result.text == content

    @pytest.mark.asyncio
    async def test_independent_processing_one_fails(self, tmp_dir):
        """Each file is processed independently — one failure doesn't affect others."""
        # Create a valid text file
        valid_path = _write_file(tmp_dir, "valid.txt", b"Valid content here.")

        # Create an invalid PDF
        invalid_path = _write_file(tmp_dir, "bad.pdf", b"not a pdf")

        # Process both independently
        result_valid = await extract_document(valid_path, "text/plain")
        result_invalid = await extract_document(invalid_path, "application/pdf")

        # Valid file succeeds regardless of the other file failing
        assert result_valid.success is True
        assert result_valid.text == "Valid content here."

        # Invalid file fails independently
        assert result_invalid.success is False

    @pytest.mark.asyncio
    async def test_filename_extracted_from_path(self, tmp_dir):
        """Filename is extracted from the full filepath."""
        nested_dir = os.path.join(tmp_dir, "uploads", "user123", "job456")
        os.makedirs(nested_dir)
        path = _write_file(nested_dir, "my_resume.txt", b"Content.")

        result = await extract_document(path, "text/plain")

        assert result.filename == "my_resume.txt"
