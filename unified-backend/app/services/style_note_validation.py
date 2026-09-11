"""Shared validation rule for style_note proposals.

Used by both profiling_agent.py (post-session inferred proposals) and
l1_fact_synthesizer.py (document-derived proposals) so a note rejected on
one path can't sail through the other under looser rules.
"""

from app.models.profile import StyleNoteCategory

MAX_NOTE_LENGTH = 140

_VALID_CATEGORIES = {c.value for c in StyleNoteCategory}


def is_valid_style_note(category: object, note: object) -> bool:
    """True if `category` is a recognized StyleNoteCategory value and `note`
    is a non-empty string within MAX_NOTE_LENGTH characters."""
    return (
        category in _VALID_CATEGORIES
        and isinstance(note, str)
        and 0 < len(note) <= MAX_NOTE_LENGTH
    )
