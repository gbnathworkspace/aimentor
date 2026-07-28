"""Unit tests for extract_pdf in document_extractor.py."""

import os
import tempfile

import pytest

from app.services.document_extractor import extract_pdf


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a simple valid PDF file for testing."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    # Add a page with some text using a simple annotation approach
    # For a clean test, we create a minimal PDF with reportlab-style content
    # pypdf's PdfWriter can create blank pages; we'll use a real PDF bytes approach
    pdf_path = tmp_path / "sample.pdf"

    # Create a minimal valid PDF with text content
    # Using fpdf2 or raw PDF construction isn't available,
    # so we'll write raw PDF bytes for a minimal document
    pdf_content = _create_minimal_pdf_with_text("Hello World\nThis is a test document.")
    pdf_path.write_bytes(pdf_content)
    return str(pdf_path)


@pytest.fixture
def multi_page_pdf(tmp_path):
    """Create a multi-page PDF."""
    pdf_path = tmp_path / "multipage.pdf"
    pdf_content = _create_multi_page_pdf(["Page one content.", "Page two content.", "Page three content."])
    pdf_path.write_bytes(pdf_content)
    return str(pdf_path)


@pytest.fixture
def corrupted_pdf(tmp_path):
    """Create a corrupted PDF file."""
    pdf_path = tmp_path / "corrupted.pdf"
    pdf_path.write_bytes(b"This is not a valid PDF file at all - just random bytes")
    return str(pdf_path)


@pytest.fixture
def empty_pdf(tmp_path):
    """Create a valid PDF with no text content."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf_path = tmp_path / "empty.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return str(pdf_path)


def _create_minimal_pdf_with_text(text: str) -> bytes:
    """Create a minimal PDF with text using raw PDF syntax."""
    # This creates a minimal but valid PDF with text content
    lines = text.split("\n")
    # Build text operations
    text_ops = ""
    y_position = 700
    for line in lines:
        # Escape special PDF characters
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text_ops += f"BT /F1 12 Tf {72} {y_position} Td ({escaped}) Tj ET\n"
        y_position -= 20

    stream_content = text_ops.encode("latin-1")
    stream_length = len(stream_content)

    pdf = b"""%PDF-1.4
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
<< /Length """ + str(stream_length).encode() + b""" >>
stream
""" + stream_content + b"""
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
""" + str(300 + stream_length + 30).encode() + b""" 00000 n 

trailer
<< /Size 6 /Root 1 0 R >>
startxref
""" + str(360 + stream_length + 30).encode() + b"""
%%EOF"""
    return pdf


def _create_multi_page_pdf(page_texts: list[str]) -> bytes:
    """Create a multi-page PDF using pypdf."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()

    for text in page_texts:
        # Create each page as a minimal single-page PDF, then merge
        single_pdf = _create_minimal_pdf_with_text(text)
        reader = PdfReader(BytesIO(single_pdf))
        writer.add_page(reader.pages[0])

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_extract_pdf_basic(sample_pdf):
    """Test basic PDF text extraction."""
    result = await extract_pdf(sample_pdf)
    assert "Hello World" in result
    assert "test document" in result


@pytest.mark.asyncio
async def test_extract_pdf_multi_page(multi_page_pdf):
    """Test multi-page PDF extraction preserves paragraph boundaries."""
    result = await extract_pdf(multi_page_pdf)
    # Pages should be separated by double newlines
    assert "Page one content." in result
    assert "Page two content." in result
    assert "Page three content." in result
    # Check double-newline separation between pages
    assert "\n\n" in result


@pytest.mark.asyncio
async def test_extract_pdf_corrupted(corrupted_pdf):
    """Test corrupted PDF raises ValueError."""
    with pytest.raises(ValueError, match="corrupted or unreadable file"):
        await extract_pdf(corrupted_pdf)


@pytest.mark.asyncio
async def test_extract_pdf_nonexistent_file():
    """Test non-existent file raises ValueError."""
    with pytest.raises((ValueError, FileNotFoundError)):
        await extract_pdf("/nonexistent/path/to/file.pdf")


@pytest.mark.asyncio
async def test_extract_pdf_empty(empty_pdf):
    """Test empty PDF returns empty string."""
    result = await extract_pdf(empty_pdf)
    # An empty PDF with no text should produce empty or whitespace-only output
    assert result.strip() == ""


@pytest.mark.asyncio
async def test_extract_pdf_password_protected(tmp_path):
    """Test password-protected PDF raises ValueError with 'password-protected'."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    # Create a PDF and encrypt it
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secretpassword")

    pdf_path = tmp_path / "encrypted.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)

    with pytest.raises(ValueError, match="password-protected"):
        await extract_pdf(str(pdf_path))
