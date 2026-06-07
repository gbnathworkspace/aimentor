"""Unit test — onboarding prompt includes today's date + YYYY-MM-DD instruction.

Validates Requirement 3.1 (deadline emitted as a real date).
"""

import datetime

from app.services.prompt_store import clear_cache, get_onboarding_prompt


def test_prompt_includes_today_and_iso_instruction():
    clear_cache()
    prompt = get_onboarding_prompt()
    today = datetime.date.today().isoformat()
    assert today in prompt, "today's date must be injected for relative-deadline math"
    assert "YYYY-MM-DD" in prompt, "must instruct an absolute ISO date format"
