"""Unit tests for TXT, MD, and RTF extraction functions."""

import os
import tempfile

import pytest

from app.services.document_extractor import extract_rtf, extract_text


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


# --- extract_text tests ---


class TestExtractText:
    @pytest.mark.asyncio
    async def test_valid_utf8_text_file(self, tmp_dir):
        """Valid UTF-8 text file is read correctly."""
        content = "Hello, world!\nThis is a test file.\n"
        path = _write_file(tmp_dir, "sample.txt", content.encode("utf-8"))

        result = await extract_text(path)

        assert result == content

    @pytest.mark.asyncio
    async def test_invalid_byte_sequences_replaced_with_fffd(self, tmp_dir):
        """Invalid byte sequences are replaced with U+FFFD."""
        # Mix valid UTF-8 with invalid bytes (0xFF, 0xFE are invalid in UTF-8)
        raw = b"Hello \xff\xfe world"
        path = _write_file(tmp_dir, "invalid.txt", raw)

        result = await extract_text(path)

        assert "\ufffd" in result
        assert "Hello" in result
        assert "world" in result

    @pytest.mark.asyncio
    async def test_md_file_treated_same_as_txt(self, tmp_dir):
        """Markdown files are treated as plain text (UTF-8)."""
        content = "# Heading\n\nSome **bold** text.\n- Item 1\n- Item 2\n"
        path = _write_file(tmp_dir, "readme.md", content.encode("utf-8"))

        result = await extract_text(path)

        assert result == content

    @pytest.mark.asyncio
    async def test_empty_text_file(self, tmp_dir):
        """Empty text file returns empty string."""
        path = _write_file(tmp_dir, "empty.txt", b"")

        result = await extract_text(path)

        assert result == ""

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_value_error(self):
        """Non-existent file raises ValueError."""
        with pytest.raises(ValueError, match="file not found"):
            await extract_text("/nonexistent/path/file.txt")

    @pytest.mark.asyncio
    async def test_unicode_content_preserved(self, tmp_dir):
        """Unicode characters (emoji, CJK, etc.) are preserved."""
        content = "日本語テスト 🎉 café résumé"
        path = _write_file(tmp_dir, "unicode.txt", content.encode("utf-8"))

        result = await extract_text(path)

        assert result == content

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_bytes(self, tmp_dir):
        """File with mixed valid UTF-8 and invalid sequences handles both."""
        # Valid UTF-8 for "café" is: 63 61 66 c3 a9
        # Insert invalid byte 0x80 (continuation byte without start byte)
        raw = b"caf\xc3\xa9 \x80 more text"
        path = _write_file(tmp_dir, "mixed.txt", raw)

        result = await extract_text(path)

        assert "café" in result
        assert "\ufffd" in result
        assert "more text" in result


# --- extract_rtf tests ---


class TestExtractRtf:
    @pytest.mark.asyncio
    async def test_valid_rtf_extraction(self, tmp_dir):
        """Valid RTF file has formatting stripped and text extracted."""
        # Minimal valid RTF document with known text
        rtf_content = rb"{\rtf1\ansi{\fonttbl\f0\fswiss Helvetica;}\f0\pard Hello RTF World\par}"
        path = _write_file(tmp_dir, "sample.rtf", rtf_content)

        result = await extract_rtf(path)

        assert "Hello RTF World" in result

    @pytest.mark.asyncio
    async def test_rtf_strips_formatting(self, tmp_dir):
        """RTF control words are removed from output."""
        rtf_content = rb"{\rtf1\ansi\deff0{\fonttbl{\f0 Times New Roman;}}\f0\fs24 Simple text content\par}"
        path = _write_file(tmp_dir, "formatted.rtf", rtf_content)

        result = await extract_rtf(path)

        assert "Simple text content" in result
        # Should not contain RTF control words
        assert "\\rtf" not in result
        assert "\\fonttbl" not in result

    @pytest.mark.asyncio
    async def test_corrupted_rtf_raises_value_error(self, tmp_dir):
        """Corrupted/invalid RTF content raises ValueError."""
        # Not valid RTF at all — just random binary
        path = _write_file(tmp_dir, "corrupted.rtf", b"\x00\x01\x02\x03\x04\x05")

        with pytest.raises(ValueError, match="corrupted or unreadable RTF file"):
            await extract_rtf(path)

    @pytest.mark.asyncio
    async def test_nonexistent_rtf_raises_value_error(self):
        """Non-existent RTF file raises ValueError."""
        with pytest.raises(ValueError, match="file not found"):
            await extract_rtf("/nonexistent/path/file.rtf")

    @pytest.mark.asyncio
    async def test_empty_rtf_file(self, tmp_dir):
        """Empty RTF file raises ValueError (not valid RTF)."""
        path = _write_file(tmp_dir, "empty.rtf", b"")

        # striprtf should raise on empty content
        with pytest.raises(ValueError, match="corrupted or unreadable RTF file"):
            await extract_rtf(path)

    @pytest.mark.asyncio
    async def test_rtf_with_multiple_paragraphs(self, tmp_dir):
        """RTF with multiple paragraphs extracts all text."""
        rtf_content = rb"{\rtf1\ansi\deff0 First paragraph\par Second paragraph\par Third paragraph\par}"
        path = _write_file(tmp_dir, "multi.rtf", rtf_content)

        result = await extract_rtf(path)

        assert "First paragraph" in result
        assert "Second paragraph" in result
        assert "Third paragraph" in result
