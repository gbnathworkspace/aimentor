"""Shared parsing for LLM responses that embed a fenced suggestions JSON block.

Used by both onboarding chat and topic/mentor chat — both prompts teach the
LLM to emit the same ```json suggestions block when it asks a question with
plausible discrete answers.
"""

import json
import re

_SUGGESTIONS_RE = re.compile(r"```json suggestions\s*\n(.*?)\n```", re.DOTALL)


def extract_suggestions(text: str) -> tuple[str, list[dict]]:
    """Strip a fenced ```json suggestions block from text and parse it.

    Returns (clean_text, suggestions) where suggestions is a list of
    {"title": str, "description": str} dicts, or [] if absent/invalid.
    """
    suggestions: list[dict] = []
    match = _SUGGESTIONS_RE.search(text)
    if match:
        try:
            suggestions = json.loads(match.group(1))
        except json.JSONDecodeError:
            suggestions = []

    clean_text = _SUGGESTIONS_RE.sub("", text).strip()
    return clean_text, suggestions
