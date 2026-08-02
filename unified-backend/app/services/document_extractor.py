"""Multi-format document text extraction for the chat upload pipeline.

Extracts text content from uploaded documents (PDF, DOCX, CSV, XLSX,
JSON, TXT, MD, RTF) and produces clean text suitable for LLM synthesis.

This module is part of the Document Ingestion Pipeline and is independent
from the existing extraction.py (which handles chunking and embedding for L3).
"""

import csv
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional
from zipfile import BadZipFile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from app.services.storage import open_for_read

logger = logging.getLogger(__name__)

MAX_DATA_ROWS = 5000
MAX_JSON_DEPTH = 10
MAX_ARRAY_ELEMENTS = 100
MAX_EXTRACTED_CHARS = 50_000


@dataclass
class ExtractionResult:
    """Result of extracting text from a single document.

    Attributes:
        filename: Original filename of the uploaded document.
        text: Extracted text content, truncated to max 50,000 characters.
        success: Whether extraction completed successfully.
        error: Error message if extraction failed, None otherwise.
    """

    filename: str
    text: str
    success: bool
    error: Optional[str] = None


def truncate_at_sentence_boundary(text: str, max_chars: int) -> str:
    """Truncate text at the nearest sentence boundary within the character limit.

    If the text is within the limit, returns it as-is. Otherwise, finds the
    last sentence-ending punctuation (`.`, `?`, `!`) followed by whitespace
    or end-of-string within the first `max_chars` characters. If no sentence
    boundary is found, performs a hard cutoff at `max_chars`.

    Args:
        text: The text to truncate.
        max_chars: Maximum number of characters allowed.

    Returns:
        Truncated text, never exceeding max_chars characters.
    """
    if len(text) <= max_chars:
        return text

    # Look for the last sentence-ending punctuation followed by whitespace
    # or end-of-string within the first max_chars characters
    search_region = text[:max_chars]

    # Find the last occurrence of sentence-ending punctuation followed by
    # whitespace or at the end of the search region
    match = None
    for m in re.finditer(r"[.!?](?:\s|$)", search_region):
        match = m

    if match:
        # Include the punctuation mark but not the trailing whitespace
        return search_region[: match.start() + 1]

    # No sentence boundary found — hard cutoff
    return search_region


async def extract_document(filepath: str, mime_type: str) -> ExtractionResult:
    """Route to appropriate extractor based on MIME type.

    Dispatches to format-specific extraction functions and handles
    common post-processing (empty content detection, text truncation).

    Args:
        filepath: Path to the uploaded file on disk.
        mime_type: MIME type of the file for format detection.

    Returns:
        ExtractionResult with extracted text or error details.
    """
    import os

    filename = os.path.basename(filepath)

    # MIME type to extractor function mapping
    mime_extractors = {
        "application/pdf": extract_pdf,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": extract_docx,
        "text/csv": extract_csv,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": extract_xlsx,
        "application/json": extract_json,
        "text/plain": extract_text,
        "text/markdown": extract_text,
        "application/rtf": extract_rtf,
    }

    # Find the appropriate extractor
    extractor = mime_extractors.get(mime_type)
    if extractor is None:
        return ExtractionResult(
            filename=filename,
            text="",
            success=False,
            error=f"unsupported MIME type: {mime_type}",
        )

    # Call the extractor, catching ValueError from individual extractors.
    # open_for_read yields a local path: S3-backed keys are downloaded to a
    # temp file, local paths pass through unchanged — extractors stay
    # path-based regardless of backend.
    try:
        with open_for_read(filepath) as local_path:
            text = await extractor(local_path)
    except ValueError as e:
        return ExtractionResult(
            filename=filename,
            text="",
            success=False,
            error=str(e),
        )

    # Check for empty content after stripping whitespace
    if not text.strip():
        return ExtractionResult(
            filename=filename,
            text="",
            success=False,
            error="no extractable content",
        )

    # Truncate at sentence boundary if text exceeds limit
    truncated_text = truncate_at_sentence_boundary(text, MAX_EXTRACTED_CHARS)

    return ExtractionResult(
        filename=filename,
        text=truncated_text,
        success=True,
        error=None,
    )


async def extract_pdf(filepath: str) -> str:
    """Extract text from a PDF file preserving paragraph boundaries.

    Represents paragraph boundaries as double newlines and section
    headings as prefixed lines followed by a newline separator.

    Args:
        filepath: Path to the PDF file.

    Returns:
        Extracted text content.

    Raises:
        ValueError: If the file is password-protected or corrupted.
    """
    from pypdf import PdfReader
    from pypdf.errors import FileNotDecryptedError, PdfReadError

    try:
        reader = PdfReader(filepath)
    except FileNotDecryptedError:
        raise ValueError("password-protected")
    except PdfReadError:
        raise ValueError("corrupted or unreadable file")
    except Exception as e:
        logger.error(f"Unexpected error opening PDF {filepath}: {e}")
        raise ValueError("corrupted or unreadable file")

    # Check if the PDF is encrypted and we can't read it
    if reader.is_encrypted:
        raise ValueError("password-protected")

    page_texts = []
    try:
        for page in reader.pages:
            text = page.extract_text()
            if text:
                page_texts.append(text.strip())
    except FileNotDecryptedError:
        raise ValueError("password-protected")
    except PdfReadError:
        raise ValueError("corrupted or unreadable file")
    except Exception as e:
        logger.error(f"Error extracting text from PDF {filepath}: {e}")
        raise ValueError("corrupted or unreadable file")

    # Join pages with double newlines to preserve paragraph boundaries
    return "\n\n".join(page_texts)


async def extract_docx(filepath: str) -> str:
    """Extract text from a DOCX file including headings, paragraphs, lists.

    Discards formatting metadata (font, color, spacing) and retains
    only the textual content structure.

    Args:
        filepath: Path to the DOCX file.

    Returns:
        Extracted text content.

    Raises:
        ValueError: If the file is corrupted or password-protected.
    """
    from zipfile import BadZipFile

    try:
        import docx
    except ImportError as e:
        raise ImportError("python-docx is required for DOCX extraction") from e

    try:
        document = docx.Document(filepath)
    except BadZipFile:
        raise ValueError("corrupted or unreadable file")
    except KeyError:
        # python-docx raises KeyError when expected XML parts are missing
        # (e.g., password-protected DOCX files that are encrypted ZIPs)
        raise ValueError("password-protected")
    except Exception as e:
        # Catch-all for other failures (e.g., encrypted/password-protected files
        # that fail at different stages, or otherwise corrupted content)
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypt" in error_msg:
            raise ValueError("password-protected")
        raise ValueError("corrupted or unreadable file")

    paragraphs = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style else ""

        if style_name.startswith("Heading"):
            # Prefix headings with their text (no additional marker needed,
            # the text itself serves as the heading)
            paragraphs.append(text)
        elif style_name.startswith("List"):
            # Add bullet marker for list items
            paragraphs.append(f"• {text}")
        else:
            paragraphs.append(text)

    return "\n\n".join(paragraphs)


async def extract_csv(filepath: str) -> str:
    """Parse CSV file into structured text with column headers and row values.

    Limits extraction to a maximum of 5000 rows. Column headers
    are always preserved.

    Args:
        filepath: Path to the CSV file.

    Returns:
        Structured text representation of the CSV data.

    Raises:
        ValueError: If the file is corrupted or cannot be parsed.
    """
    try:
        with open(filepath, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            rows = []
            for i, row in enumerate(reader):
                rows.append(row)
                # First row (i=0) is header, then up to MAX_DATA_ROWS data rows
                if i >= MAX_DATA_ROWS:
                    break

            if not rows:
                raise ValueError("CSV file is empty")

            header = rows[0]
            data_rows = rows[1:]

            lines = [" | ".join(header), "---"]
            for row in data_rows:
                # Pad or truncate row to match header length
                padded = row[:len(header)] + [""] * max(0, len(header) - len(row))
                lines.append(" | ".join(padded))

            return "\n".join(lines)
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to extract CSV from {filepath}: {e}")
        raise ValueError(f"Failed to parse CSV file: {e}")


async def extract_xlsx(filepath: str) -> str:
    """Parse XLSX file (first sheet) into structured text.

    Limits extraction to a maximum of 5000 rows. Column headers
    are always preserved. Uses openpyxl for reading.

    Args:
        filepath: Path to the XLSX file.

    Returns:
        Structured text representation of the spreadsheet data.

    Raises:
        ValueError: If the file is corrupted or cannot be read.
    """
    try:
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active

        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            # Convert cell values to strings, treating None as empty
            str_row = [str(cell) if cell is not None else "" for cell in row]
            rows.append(str_row)
            # First row (i=0) is header, then up to MAX_DATA_ROWS data rows
            if i >= MAX_DATA_ROWS:
                break

        wb.close()

        if not rows:
            raise ValueError("XLSX file is empty")

        header = rows[0]
        data_rows = rows[1:]

        lines = [" | ".join(header), "---"]
        for row in data_rows:
            # Pad or truncate row to match header length
            padded = row[:len(header)] + [""] * max(0, len(header) - len(row))
            lines.append(" | ".join(padded))

        return "\n".join(lines)
    except (InvalidFileException, BadZipFile) as e:
        logger.error(f"Failed to extract XLSX from {filepath}: {e}")
        raise ValueError(f"Failed to parse XLSX file: {e}")
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to extract XLSX from {filepath}: {e}")
        raise ValueError(f"Failed to parse XLSX file: {e}")


async def extract_json(filepath: str) -> str:
    """Parse JSON and produce flattened key-path/value text representation.

    Traverses nested objects up to 10 levels deep and truncates
    arrays to the first 100 elements.

    Args:
        filepath: Path to the JSON file.

    Returns:
        Flattened text representation of the JSON structure.

    Raises:
        ValueError: If the file contains malformed JSON.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON: {e}")
    except Exception as e:
        raise ValueError(f"Failed to read JSON file: {e}")

    lines: list[str] = []
    _flatten_json(data, "root", 0, lines)
    return "\n".join(lines)


def _flatten_json(value: Any, path: str, depth: int, lines: list[str]) -> None:
    """Recursively flatten a JSON value into key-path: value lines.

    Args:
        value: The current JSON value being processed.
        path: The dot-separated key path to this value.
        depth: Current nesting depth (0-based).
        lines: Accumulator list for output lines.
    """
    if depth >= MAX_JSON_DEPTH:
        return

    if isinstance(value, dict):
        if not value:
            lines.append(f"{path}: {{}}")
            return
        for key, val in value.items():
            child_path = f"{path}.{key}"
            _flatten_json(val, child_path, depth + 1, lines)
    elif isinstance(value, list):
        if not value:
            lines.append(f"{path}: []")
            return
        for i, item in enumerate(value[:MAX_ARRAY_ELEMENTS]):
            child_path = f"{path}[{i}]"
            _flatten_json(item, child_path, depth + 1, lines)
    else:
        lines.append(f"{path}: {value}")


async def extract_text(filepath: str) -> str:
    """Read TXT or MD file as UTF-8 text.

    Replaces any invalid byte sequences with the Unicode
    replacement character (U+FFFD).

    Args:
        filepath: Path to the text/markdown file.

    Returns:
        UTF-8 text content with invalid bytes replaced.

    Raises:
        ValueError: If the file cannot be read.
    """
    try:
        with open(filepath, "rb") as f:
            raw_bytes = f.read()
    except FileNotFoundError:
        raise ValueError("file not found")
    except OSError as e:
        logger.error(f"Failed to read text file {filepath}: {e}")
        raise ValueError("corrupted or unreadable file")

    return raw_bytes.decode("utf-8", errors="replace")


async def extract_rtf(filepath: str) -> str:
    """Strip RTF formatting and extract plain text content.

    Uses striprtf to remove RTF control words and formatting
    markers, producing clean plain text.

    Args:
        filepath: Path to the RTF file.

    Returns:
        Plain text content extracted from the RTF file.

    Raises:
        ValueError: If the file cannot be read or RTF parsing fails.
    """
    try:
        with open(filepath, "rb") as f:
            raw_bytes = f.read()
    except FileNotFoundError:
        raise ValueError("file not found")
    except OSError as e:
        logger.error(f"Failed to read RTF file {filepath}: {e}")
        raise ValueError("corrupted or unreadable RTF file")

    try:
        from striprtf.striprtf import rtf_to_text

        content = raw_bytes.decode("latin-1")

        # RTF files must start with {\rtf — reject anything else
        if not content.strip().startswith("{\\rtf"):
            raise ValueError("corrupted or unreadable RTF file")

        return rtf_to_text(content)
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to parse RTF file {filepath}: {e}")
        raise ValueError("corrupted or unreadable RTF file")
