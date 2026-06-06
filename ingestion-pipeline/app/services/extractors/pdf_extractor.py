"""PDF text extraction with section-aware parsing using PyMuPDF."""

import re

import fitz  # PyMuPDF

from app.models.schemas import ResumeSection


class ExtractionError(Exception):
    """Raised when PDF extraction fails or produces insufficient content."""

    pass


# Section heading patterns mapped to their normalized names
SECTION_PATTERNS: dict[str, list[str]] = {
    "work_experience": [
        "work experience",
        "professional experience",
        "employment history",
        "experience",
    ],
    "education": [
        "education",
        "academic background",
        "qualifications",
    ],
    "skills": [
        "skills",
        "technical skills",
        "core competencies",
        "technologies",
    ],
    "projects": [
        "projects",
        "personal projects",
        "key projects",
    ],
}


def _build_section_regex() -> re.Pattern:
    """Build a compiled regex that matches any known section heading on its own line.

    Headings may have optional trailing colons or whitespace.
    Longer patterns are tried first to avoid partial matches
    (e.g., "work experience" before "experience").
    """
    all_patterns: list[str] = []
    for variants in SECTION_PATTERNS.values():
        all_patterns.extend(variants)
    # Sort by length descending so longer matches take priority
    all_patterns.sort(key=len, reverse=True)
    escaped = [re.escape(p) for p in all_patterns]
    joined = "|".join(escaped)
    # Match heading on its own line, optional colon/whitespace after
    return re.compile(
        rf"^\s*({joined})\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )


SECTION_HEADING_RE = _build_section_regex()

# Reverse lookup: pattern text -> normalized section name
_PATTERN_TO_SECTION: dict[str, str] = {}
for section_name, variants in SECTION_PATTERNS.items():
    for variant in variants:
        _PATTERN_TO_SECTION[variant.lower()] = section_name


def _normalize_section_name(heading_text: str) -> str:
    """Map a detected heading to its normalized section name."""
    cleaned = heading_text.strip().rstrip(":").strip().lower()
    return _PATTERN_TO_SECTION.get(cleaned, "other")


def _is_sub_heading(line: str) -> bool:
    """Heuristic to detect sub-headings within a section.

    A sub-heading is a line that:
    - Is shorter than 80 characters
    - Does not end with common sentence-ending punctuation (. ! ?)
    - Is not empty
    """
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) >= 80:
        return False
    if stripped[-1] in ".!?":
        return False
    return True


def _extract_sub_entries(text: str) -> list[str]:
    """Extract sub-headings from a section's text content.

    A sub-heading is identified as a short line that doesn't end with
    sentence punctuation and appears before longer text blocks.
    """
    lines = text.split("\n")
    sub_entries: list[str] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if not _is_sub_heading(stripped):
            continue

        # Check if this line appears before a longer text block
        # (i.e., subsequent non-empty lines exist that are longer or sentence-like)
        has_following_content = False
        for j in range(i + 1, min(i + 5, len(lines))):
            following = lines[j].strip()
            if following and (len(following) >= 80 or following[-1] in ".!?"):
                has_following_content = True
                break

        if has_following_content:
            sub_entries.append(stripped)

    return sub_entries


class PDFExtractor:
    """Extracts section-aware text from resume PDFs using PyMuPDF (fitz)."""

    def extract(self, file_bytes: bytes) -> list[ResumeSection]:
        """Extract text from PDF bytes and parse into resume sections.

        Args:
            file_bytes: Raw PDF file content as bytes.

        Returns:
            List of ResumeSection objects with detected sections.

        Raises:
            ExtractionError: If extracted text has fewer than 10 characters.
        """
        raw_text = self._extract_raw_text(file_bytes)

        if len(raw_text.strip()) < 10:
            raise ExtractionError(
                "Extracted text is too short (fewer than 10 characters). "
                "The PDF may be empty, image-only, or corrupted."
            )

        sections = self._detect_sections(raw_text)

        if not sections:
            # No recognized sections found — return as unstructured
            return [
                ResumeSection(
                    section="unstructured",
                    text=raw_text.strip(),
                    order=0,
                    sub_entries=_extract_sub_entries(raw_text),
                )
            ]

        return sections

    def _extract_raw_text(self, file_bytes: bytes) -> str:
        """Extract raw text from PDF bytes using PyMuPDF.

        Opens the PDF from bytes stream and concatenates text from all pages.
        """
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_text: list[str] = []

        for page in doc:
            page_text = page.get_text()
            if page_text:
                pages_text.append(page_text)

        doc.close()
        return "\n".join(pages_text)

    def _detect_sections(self, text: str) -> list[ResumeSection]:
        """Detect section headings and split text into ResumeSection objects.

        Uses regex patterns to find known section headings, then splits the
        text at those points into separate sections.
        """
        matches = list(SECTION_HEADING_RE.finditer(text))

        if not matches:
            return []

        sections: list[ResumeSection] = []

        for i, match in enumerate(matches):
            heading_text = match.group(1)
            section_name = _normalize_section_name(heading_text)

            # Section text starts after the heading line
            start = match.end()

            # Section text ends at the next heading or end of document
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(text)

            section_text = text[start:end].strip()

            sub_entries = _extract_sub_entries(section_text)

            sections.append(
                ResumeSection(
                    section=section_name,
                    text=section_text,
                    order=i,
                    sub_entries=sub_entries,
                )
            )

        return sections
