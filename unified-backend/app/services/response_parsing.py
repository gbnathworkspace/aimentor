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


_QUIZ_RE = re.compile(r"```json quiz\s*\n(.*?)\n```", re.DOTALL)
_QUIZ_IDS = ["A", "B", "C", "D"]


def _valid_quiz(q) -> bool:
    """The fixed MCQ template (.kiro/specs/mcq-quiz Req 1.2) — anything else
    is dropped rather than rendered as a broken card."""
    if not isinstance(q, dict):
        return False
    opts = q.get("options")
    if not (isinstance(opts, list) and [o.get("id") if isinstance(o, dict) else None for o in opts] == _QUIZ_IDS):
        return False
    if not all(isinstance(o.get("text"), str) and o["text"].strip() for o in opts):
        return False
    if q.get("answer") not in _QUIZ_IDS:
        return False
    if not (isinstance(q.get("stem"), str) and q["stem"].strip() and isinstance(q.get("why"), str) and q["why"].strip()):
        return False
    # Req 1.3: every wrong option names the mistake behind it.
    mis = q.get("misconceptions")
    wrong = [i for i in _QUIZ_IDS if i != q["answer"]]
    if not (isinstance(mis, dict) and all(isinstance(mis.get(i), str) and mis[i].strip() for i in wrong)):
        return False
    n, total = q.get("q"), q.get("of")
    return isinstance(n, int) and isinstance(total, int) and 1 <= n <= total


def extract_quiz(text: str) -> tuple[str, dict | None]:
    """Strip a fenced ```json quiz block and return (clean_text, quiz).

    quiz is None when absent, unparseable, or off-template. Only the first
    block counts — the template is one question per turn.
    """
    quiz = None
    match = _QUIZ_RE.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            parsed = None
        if _valid_quiz(parsed):
            quiz = {k: parsed[k] for k in ("q", "of", "stem", "options", "answer", "why", "misconceptions")}
            for k in ("subtopic", "code", "styleBrief"):
                if parsed.get(k):
                    quiz[k] = parsed[k]
    return _QUIZ_RE.sub("", text).strip(), quiz
