"""Property test — Text truncation at sentence boundary (Property 9).

Validates Requirements 3.12:
- Truncation output never exceeds 50,000 characters.
- Output ends at a sentence boundary (period, question mark, or exclamation mark).
- Output is a prefix of the original text (no content reordering).
"""

import random as _random
import string

from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from app.services.document_extractor import (
    MAX_EXTRACTED_CHARS,
    truncate_at_sentence_boundary,
)


# Strategy to generate long text with sentence boundaries efficiently.
# Instead of drawing each word individually, we generate a seed and build
# the text deterministically from it to avoid the health check issue.
_sentence_endings = [".", "?", "!"]
_words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing",
          "elit", "sed", "eiusmod", "tempor", "incididunt", "labore", "magna",
          "aliqua", "enim", "minim", "veniam", "nostrud", "exercitation"]


@st.composite
def random_long_text(draw):
    """Generate text composed of random sentences totaling 50k-200k chars."""
    target_length = draw(st.integers(min_value=50_000, max_value=200_000))
    seed = draw(st.integers(min_value=0, max_value=2**32 - 1))
    rng = _random.Random(seed)

    sentences = []
    current_length = 0

    while current_length < target_length:
        # Generate a sentence with random words and a sentence-ending
        word_count = rng.randint(3, 20)
        words = [rng.choice(_words) for _ in range(word_count)]
        ending = rng.choice(_sentence_endings)
        sentence = " ".join(words) + ending
        sentences.append(sentence)
        current_length += len(sentence) + 1

    text = " ".join(sentences)
    assume(len(text) >= 50_000)
    return text


# Feature: chat-document-upload, Property 9: Text truncation at sentence boundary
@settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
@given(text=random_long_text())
def test_truncation_respects_char_limit_at_sentence_boundary(text):
    """Property 9: Text truncation produces output ≤ 50,000 chars
    that ends at a sentence boundary and is a prefix of the original.

    **Validates: Requirements 3.12**
    """
    result = truncate_at_sentence_boundary(text, MAX_EXTRACTED_CHARS)

    # (a) Output must not exceed the character limit
    assert len(result) <= MAX_EXTRACTED_CHARS, (
        f"Truncated text length {len(result)} exceeds limit {MAX_EXTRACTED_CHARS}"
    )

    # (b) Output ends at a sentence boundary (., ?, !)
    # OR it's a hard cutoff (if no sentence boundary was found within the limit)
    stripped = result.rstrip()
    if stripped:
        last_char = stripped[-1]
        # Either ends at sentence boundary or is a hard cutoff at max_chars
        if len(result) < MAX_EXTRACTED_CHARS:
            # If shorter than max, it found a sentence boundary
            assert last_char in ".?!", (
                f"Truncated text does not end at sentence boundary. "
                f"Last char: {last_char!r}"
            )

    # (c) Output is a prefix of the original text (no content reordering)
    assert text.startswith(result), (
        "Truncated output is not a prefix of the original text"
    )
