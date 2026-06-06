"""Property-based tests for PDF section detection."""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.extractors.pdf_extractor import (
    PDFExtractor,
    SECTION_PATTERNS,
    _normalize_section_name,
)


# Generate valid section headings from SECTION_PATTERNS
ALL_HEADINGS = []
for variants in SECTION_PATTERNS.values():
    ALL_HEADINGS.extend(variants)

heading_strategy = st.sampled_from(ALL_HEADINGS)

# Generate random non-empty text content (avoiding section heading patterns)
content_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" .,;!?-"),
    min_size=10,
    max_size=200,
).filter(lambda t: t.strip() and len(t.strip()) >= 10)


@st.composite
def text_with_sections(draw):
    """Generate a text block with 1-4 recognized section headings and random content between them."""
    num_sections = draw(st.integers(min_value=1, max_value=4))
    headings = draw(
        st.lists(heading_strategy, min_size=num_sections, max_size=num_sections, unique=True)
    )

    parts = []
    for heading in headings:
        # Add heading on its own line
        parts.append(f"\n{heading}\n")
        # Add content after the heading
        content = draw(content_text)
        parts.append(content + "\n")

    return "".join(parts)


# Feature: ingestion-pipeline, Property 3: PDF section detection
class TestPDFSectionDetection:
    """Property 3: PDF section detection.

    For any text block with recognized section headings, the _detect_sections method
    returns section objects with non-empty section names and text.
    """

    @given(text_block=text_with_sections())
    @settings(max_examples=100)
    def test_detect_sections_returns_nonempty_sections(self, text_block: str):
        """**Validates: Requirements 2.2, 2.3**

        For any text block with recognized section headings, _detect_sections returns
        section objects with non-empty section names and non-empty text.
        """
        extractor = PDFExtractor()
        sections = extractor._detect_sections(text_block)

        # Must detect at least one section since we generated text with headings
        assert len(sections) >= 1

        for section in sections:
            # Each section must have a non-empty section name
            assert section.section.strip() != ""
            # Section name must be a recognized normalized name
            assert section.section in SECTION_PATTERNS or section.section == "other"
            # Each section must have non-empty text
            assert section.text.strip() != ""
            # Order must be non-negative
            assert section.order >= 0
