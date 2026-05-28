import json
import anthropic
from core.config import settings
from core.models import SessionEndOutput
from .prompts import INTENT_CHECK_PROMPT, SESSION_END_PROMPT, TITLE_PROMPT

_sonnet = "claude-sonnet-4-6"
_haiku = "claude-haiku-4-5-20251001"

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def check_intent_needs_context(message: str) -> bool:
    response = _client.messages.create(
        model=_haiku,
        max_tokens=5,
        messages=[{"role": "user", "content": INTENT_CHECK_PROMPT.format(message=message)}],
    )
    answer = response.content[0].text.strip().lower()
    return answer == "yes"


def generate_session_end(transcript: list[dict]) -> SessionEndOutput:
    formatted = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in transcript
    )
    response = _client.messages.create(
        model=_sonnet,
        max_tokens=1024,
        messages=[{"role": "user", "content": SESSION_END_PROMPT.format(transcript=formatted)}],
    )
    raw = response.content[0].text.strip()
    data = json.loads(raw)
    return SessionEndOutput(**data)


def generate_title(summary: str) -> str:
    response = _client.messages.create(
        model=_haiku,
        max_tokens=20,
        messages=[{"role": "user", "content": TITLE_PROMPT.format(summary=summary)}],
    )
    return response.content[0].text.strip()


def stream_chat(system_prompt: str, messages: list[dict]):
    """Yields text chunks from Claude Sonnet via streaming."""
    with _client.messages.stream(
        model=_sonnet,
        max_tokens=2048,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
