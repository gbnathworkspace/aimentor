"""Property tests — Document extraction correctness (Properties 4, 5, 6, 7).

Validates Requirements 3.3, 3.4, 3.5, 3.6, 3.7:
- Tabular extraction respects row limits (CSV/XLSX).
- JSON flattening respects depth and array limits.
- UTF-8 text extraction replaces invalid bytes.
- RTF extraction preserves text content.
"""

import asyncio
import csv
import json
import os
import tempfile

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.document_extractor import (
    MAX_ARRAY_ELEMENTS,
    MAX_DATA_ROWS,
    MAX_JSON_DEPTH,
    extract_csv,
    extract_xlsx,
    extract_document,
    extract_json,
    extract_rtf,
    extract_text,
)


# ──────────────────────────────────────────────────────────────────────────────
# Property 4: Tabular extraction respects row limits
# **Validates: Requirements 3.3, 3.4**
# ──────────────────────────────────────────────────────────────────────────────


# Feature: chat-document-upload, Property 4: Tabular extraction respects row limits (CSV)
@settings(max_examples=100)
@given(
    num_cols=st.integers(min_value=1, max_value=10),
    num_rows=st.integers(min_value=0, max_value=10000),
)
def test_csv_extraction_respects_row_limit(num_cols, num_rows):
    """Property 4: CSV extraction output never exceeds 5000 data rows
    and always preserves headers.

    **Validates: Requirements 3.3**
    """
    # Generate header
    header = [f"col_{i}" for i in range(num_cols)]

    # Write CSV to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row_idx in range(num_rows):
            writer.writerow([f"val_{row_idx}_{col}" for col in range(num_cols)])
        filepath = f.name

    try:
        result = asyncio.run(extract_csv(filepath))
        lines = result.split("\n")

        # First line is the header
        assert lines[0] == " | ".join(header)
        # Second line is separator
        assert lines[1] == "---"

        # Data rows are lines after header and separator
        data_lines = lines[2:]
        # Filter empty trailing lines
        data_lines = [l for l in data_lines if l.strip()]

        # Output should have at most MAX_DATA_ROWS data rows
        assert len(data_lines) <= MAX_DATA_ROWS

        # If input rows <= limit, all rows should appear
        if num_rows <= MAX_DATA_ROWS:
            assert len(data_lines) == num_rows
        else:
            # If input exceeds limit, exactly MAX_DATA_ROWS data rows
            assert len(data_lines) == MAX_DATA_ROWS
    finally:
        os.unlink(filepath)


# Feature: chat-document-upload, Property 4: Tabular extraction respects row limits (XLSX)
@settings(max_examples=100, deadline=None)
@given(
    num_cols=st.integers(min_value=1, max_value=10),
    num_rows=st.integers(min_value=0, max_value=10000),
)
def test_xlsx_extraction_respects_row_limit(num_cols, num_rows):
    """Property 4: XLSX extraction output never exceeds 5000 data rows
    and always preserves headers.

    **Validates: Requirements 3.4**
    """
    import openpyxl

    # Create XLSX workbook with the specified rows
    wb = openpyxl.Workbook()
    ws = wb.active
    header = [f"col_{i}" for i in range(num_cols)]
    ws.append(header)
    for row_idx in range(num_rows):
        ws.append([f"val_{row_idx}_{col}" for col in range(num_cols)])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        filepath = f.name
    wb.save(filepath)
    wb.close()

    try:
        result = asyncio.run(extract_xlsx(filepath))
        lines = result.split("\n")

        # First line is the header
        assert lines[0] == " | ".join(header)
        # Second line is separator
        assert lines[1] == "---"

        # Data rows are lines after header and separator
        data_lines = lines[2:]
        # Filter empty trailing lines
        data_lines = [l for l in data_lines if l.strip()]

        # Output should have at most MAX_DATA_ROWS data rows
        assert len(data_lines) <= MAX_DATA_ROWS

        # If input rows <= limit, all rows should appear
        if num_rows <= MAX_DATA_ROWS:
            assert len(data_lines) == num_rows
        else:
            # If input exceeds limit, exactly MAX_DATA_ROWS data rows
            assert len(data_lines) == MAX_DATA_ROWS
    finally:
        os.unlink(filepath)


# ──────────────────────────────────────────────────────────────────────────────
# Property 5: JSON flattening respects depth and array limits
# **Validates: Requirements 3.5**
# ──────────────────────────────────────────────────────────────────────────────


def _build_nested_json(depth: int, array_size: int) -> dict:
    """Build a JSON structure with controlled nesting and array sizes."""
    if depth <= 0:
        return {"leaf": "value"}
    return {
        "level": depth,
        "items": [{"idx": i} for i in range(array_size)],
        "nested": _build_nested_json(depth - 1, array_size),
    }


# Feature: chat-document-upload, Property 5: JSON flattening respects depth and array limits
@settings(max_examples=100)
@given(
    depth=st.integers(min_value=0, max_value=15),
    array_size=st.integers(min_value=0, max_value=200),
)
def test_json_flattening_respects_depth_and_array_limits(depth, array_size):
    """Property 5: JSON flattening never traverses beyond depth 10 and
    truncates arrays to 100 elements.

    **Validates: Requirements 3.5**
    """
    data = _build_nested_json(depth, array_size)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = asyncio.run(extract_json(filepath))
        lines = result.split("\n")

        for line in lines:
            if not line.strip():
                continue

            # Extract the key path (before the ": " separator)
            path_part = line.split(": ", 1)[0]

            # Check depth: count dots (each dot = one level deeper)
            # root.level.nested.level... => root is depth 0
            parts = path_part.replace("[", ".").replace("]", "").split(".")
            # root counts as depth 0, so the depth is len(parts) - 1
            actual_depth = len(parts) - 1
            assert actual_depth <= MAX_JSON_DEPTH, (
                f"Depth {actual_depth} exceeds max {MAX_JSON_DEPTH}: {path_part}"
            )

            # Check array indices: no index should be >= MAX_ARRAY_ELEMENTS
            import re
            indices = re.findall(r"\[(\d+)\]", path_part)
            for idx_str in indices:
                idx = int(idx_str)
                assert idx < MAX_ARRAY_ELEMENTS, (
                    f"Array index {idx} >= max {MAX_ARRAY_ELEMENTS}: {path_part}"
                )
    finally:
        os.unlink(filepath)


# ──────────────────────────────────────────────────────────────────────────────
# Property 6: UTF-8 text extraction replaces invalid bytes
# **Validates: Requirements 3.6**
# ──────────────────────────────────────────────────────────────────────────────


# Feature: chat-document-upload, Property 6: UTF-8 text extraction replaces invalid bytes
@settings(max_examples=100)
@given(raw_bytes=st.binary(min_size=1, max_size=5000))
def test_utf8_extraction_replaces_invalid_bytes(raw_bytes):
    """Property 6: Text extraction always produces valid UTF-8 output
    and replaces invalid byte sequences with U+FFFD.

    **Validates: Requirements 3.6**
    """
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".txt", delete=False
    ) as f:
        f.write(raw_bytes)
        filepath = f.name

    try:
        result = asyncio.run(extract_text(filepath))

        # Output must be a valid string (Python strings are always valid UTF-8)
        assert isinstance(result, str)

        # Verify it can be encoded to UTF-8 without error
        result.encode("utf-8")

        # If input had invalid UTF-8, output should contain replacement char
        try:
            raw_bytes.decode("utf-8")
            # Valid UTF-8 input — output should equal decoded input
            assert result == raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Invalid UTF-8 input — output should contain replacement character
            assert "\ufffd" in result
    finally:
        os.unlink(filepath)


# ──────────────────────────────────────────────────────────────────────────────
# Property 7: RTF extraction preserves text content
# **Validates: Requirements 3.7**
# ──────────────────────────────────────────────────────────────────────────────


# Strategy for printable ASCII text (safe for RTF embedding and latin-1 encoding)
_rtf_safe_text = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        blacklist_characters="\\{}",
    ),
    min_size=1,
    max_size=500,
).filter(lambda s: s.strip())


# Feature: chat-document-upload, Property 7: RTF extraction preserves text content
@settings(max_examples=100)
@given(text_content=_rtf_safe_text)
def test_rtf_extraction_preserves_text(text_content):
    """Property 7: RTF extraction recovers the original text content
    from a valid RTF wrapper.

    **Validates: Requirements 3.7**
    """
    # Wrap text in minimal RTF structure
    rtf_content = r"{\rtf1\ansi " + text_content + r" \par}"

    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".rtf", delete=False
    ) as f:
        f.write(rtf_content.encode("latin-1"))
        filepath = f.name

    try:
        result = asyncio.run(extract_rtf(filepath))

        # The original text should appear in the extracted output
        # (striprtf may add/remove whitespace, so check containment)
        # Normalize whitespace for comparison
        normalized_input = " ".join(text_content.split())
        normalized_output = " ".join(result.split())

        assert normalized_input in normalized_output, (
            f"Original text not found in RTF extraction output.\n"
            f"Input: {normalized_input!r}\n"
            f"Output: {normalized_output!r}"
        )
    finally:
        os.unlink(filepath)
