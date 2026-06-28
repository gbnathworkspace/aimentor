"""Unit tests for MentorRequest mode validation (issue #6).

An unknown chat `mode` must be rejected at request-validation time (422),
never reach get_system_prompt, and never 500 the mentor endpoint.
"""

import pytest
from pydantic import ValidationError

from app.models.chat import MentorRequest
from app.routers.sessions import SessionUpdate

_VALID_MODES = ["planning", "topic", "doubt", "evaluation"]
_MESSAGES = [{"role": "user", "content": "hi"}]


class TestMentorRequestMode:
    @pytest.mark.parametrize("mode", _VALID_MODES)
    def test_accepts_each_valid_mode(self, mode):
        req = MentorRequest(topic="graphs", mode=mode, messages=_MESSAGES)
        assert req.mode == mode

    def test_mode_defaults_to_topic(self):
        req = MentorRequest(topic="graphs", messages=_MESSAGES)
        assert req.mode == "topic"

    @pytest.mark.parametrize("bad", ["Topic", "eval", "", "PLANNING", "chat", "x" * 50])
    def test_rejects_unknown_mode(self, bad):
        with pytest.raises(ValidationError):
            MentorRequest(topic="graphs", mode=bad, messages=_MESSAGES)


class TestSessionUpdateMode:
    """PATCH /api/sessions is the other mode entry point flagged in issue #6."""

    @pytest.mark.parametrize("mode", _VALID_MODES)
    def test_accepts_each_valid_mode(self, mode):
        assert SessionUpdate(mode=mode).mode == mode

    def test_mode_is_optional(self):
        assert SessionUpdate(title="renamed").mode is None

    def test_rejects_unknown_mode(self):
        with pytest.raises(ValidationError):
            SessionUpdate(mode="Topic")
