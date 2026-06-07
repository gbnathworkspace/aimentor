import anthropic
from app.core.config import settings

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
