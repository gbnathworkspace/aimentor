"""Property test — Independent file processing (Property 8).

Validates Requirements 3.11, 9.4:
- One file's failure does not block extraction of remaining files.
- Valid files succeed regardless of how many other files in the batch fail.
"""

import asyncio
import os
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.document_extractor import extract_document


# ──────────────────────────────────────────────────────────────────────────────
# Property 8: Independent file processing — one failure does not block others
# **Validates: Requirements 3.11, 9.4**
# ──────────────────────────────────────────────────────────────────────────────


# Feature: chat-document-upload, Property 8: Independent file processing
@settings(max_examples=100)
@given(
    valid_count=st.integers(min_value=1, max_value=5),
    corrupted_count=st.integers(min_value=1, max_value=5),
)
def test_independent_file_processing(valid_count, corrupted_count):
    """Property 8: Valid files succeed regardless of other files in the batch
    failing extraction. The count of successful extractions equals the count
    of valid files in the input.

    **Validates: Requirements 3.11, 9.4**
    """
    temp_files = []
    valid_paths = []
    corrupted_paths = []

    try:
        # Create valid text files
        for i in range(valid_count):
            f = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            )
            f.write(f"This is valid document content number {i}. It has text.")
            f.close()
            valid_paths.append(f.name)
            temp_files.append(f.name)

        # Create corrupted files (random bytes claiming to be XLSX)
        for i in range(corrupted_count):
            f = tempfile.NamedTemporaryFile(
                mode="wb", suffix=".xlsx", delete=False
            )
            f.write(b"\x00\x01\x02\x03\x04corrupted_binary_garbage" * 10)
            f.close()
            corrupted_paths.append(f.name)
            temp_files.append(f.name)

        # Process all files independently (interleaved order to ensure
        # corrupted files don't affect valid ones regardless of position)
        results = []
        all_paths = []
        all_mimes = []

        # Interleave valid and corrupted files
        vi, ci = 0, 0
        while vi < valid_count or ci < corrupted_count:
            if vi < valid_count:
                all_paths.append(valid_paths[vi])
                all_mimes.append("text/plain")
                vi += 1
            if ci < corrupted_count:
                all_paths.append(corrupted_paths[ci])
                all_mimes.append(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                ci += 1

        for path, mime in zip(all_paths, all_mimes):
            result = asyncio.run(extract_document(path, mime))
            results.append(result)

        # Key assertion: valid file count matches successful extraction count
        successful_count = sum(1 for r in results if r.success)
        assert successful_count == valid_count, (
            f"Expected {valid_count} successful extractions, got {successful_count}"
        )

        # All corrupted files should fail
        failed_count = sum(1 for r in results if not r.success)
        assert failed_count == corrupted_count, (
            f"Expected {corrupted_count} failed extractions, got {failed_count}"
        )
    finally:
        for path in temp_files:
            if os.path.exists(path):
                os.unlink(path)
