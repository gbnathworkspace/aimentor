"""Shared helpers for pulling JSON out of LLM text output.

LLMs sometimes wrap JSON in markdown code fences despite instructions, or
pad it with prose before/after. These helpers tolerate both: strip fences,
try a direct parse, then fall back to slicing out the outermost bracket/
brace pair. Return None (never raise) when nothing usable is found —
callers decide what "no JSON" means for them (raise, fall back, etc).
"""

import json
import re

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def extract_json_array(text: str) -> list | None:
    """Parse a JSON array out of `text`, or None if none can be found."""
    stripped = _strip_fences(text)
    try:
        data = json.loads(stripped)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    start, end = stripped.find("["), stripped.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return None


def extract_json_object(text: str) -> dict | None:
    """Parse a JSON object out of `text`, or None if none can be found."""
    stripped = _strip_fences(text)
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None
