"""Unit tests for the prompt store service."""

import pytest

from datetime import datetime, timezone

from app.services.prompt_store import (
    clear_cache,
    get_onboarding_prompt,
    get_system_prompt,
    _format_learning_context,
    _format_style_notes,
    _format_subtopic_mastery,
    _format_summary_blocks,
    _format_taught_concepts,
    _interpolate,
)


@pytest.fixture(autouse=True)
def _clear_prompt_cache():
    """Clear the prompt cache before each test."""
    clear_cache()
    yield
    clear_cache()


class TestGetSystemPrompt:
    """Tests for get_system_prompt function."""

    def test_returns_string_for_valid_mode(self):
        context = {
            "profile": {"goal": "Learn Python", "deadline": "2025-12-31"},
            "skill": {"topic": "Python Basics", "current_level": "beginner"},
            "episodes": [],
        }
        result = get_system_prompt("socratic", context)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_mode_instructions_socratic(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("socratic", context)
        assert "SOCRATIC mode" in result
        assert "leading question" in result

    def test_includes_mode_instructions_diagnostic(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("diagnostic", context)
        assert "DIAGNOSTIC" in result
        assert "record_diagnostic_verdict" in result

    def test_includes_mode_instructions_direct(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("direct", context)
        assert "DIRECT mode" in result
        assert "no leading question" in result

    def test_includes_mode_instructions_hint(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("hint", context)
        assert "HINT mode" in result

    def test_includes_mode_instructions_guided(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("guided", context)
        assert "GUIDED mode" in result
        assert "step 1" in result.lower()

    def test_raises_for_unknown_mode(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        with pytest.raises(ValueError, match="Unknown mode"):
            get_system_prompt("unknown_mode", context)

    def test_uses_topic_from_context_when_skill_missing(self):
        context = {
            "profile": {},
            "skill": {},
            "episodes": [],
            "topic": "Graphs",
        }
        result = get_system_prompt("socratic", context)
        assert "Graphs" in result

    def test_tone_instructions_injected(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        assert "TOUGH" in get_system_prompt("socratic", context, "tough")
        assert "ENCOURAGING" in get_system_prompt("socratic", context, "encouraging")

    def test_tone_defaults_to_balanced(self):
        # No tone arg → balanced voice, and the placeholder is always filled.
        result = get_system_prompt("socratic", context={"profile": {}, "skill": {}, "episodes": []})
        assert "BALANCED" in result
        assert "{{tone_instructions}}" not in result


class TestFormatLearningContext:
    """Topic Scoping: l1_scope filters _format_learning_context's output."""

    @pytest.fixture
    def profile(self):
        return {
            "learning_context_detail": {
                "situations": [
                    "preparing for interview backend engineer",
                    "casually looking for frontend",
                    "senior backend, Mumbai",
                ],
            }
        }

    def _judgment(self, text: str, verdict: str) -> dict:
        return {"situation": text, "verdict": verdict, "reason": "because"}

    def test_l1_scope_none_is_unfiltered(self, profile):
        result = _format_learning_context(profile, l1_scope=None)
        assert "preparing for interview backend engineer" in result
        assert "casually looking for frontend" in result
        assert "senior backend, Mumbai" in result

    def test_l1_scope_empty_list_is_not_specified(self, profile):
        assert _format_learning_context(profile, l1_scope=[]) == "Not specified"

    def test_l1_scope_filters_to_relevant_only(self, profile):
        l1_scope = [
            self._judgment("preparing for interview backend engineer", "relevant"),
            self._judgment("casually looking for frontend", "irrelevant"),
            self._judgment("senior backend, Mumbai", "relevant"),
        ]
        result = _format_learning_context(profile, l1_scope=l1_scope)
        assert "preparing for interview backend engineer" in result
        assert "senior backend, Mumbai" in result
        assert "casually looking for frontend" not in result

    def test_all_irrelevant_is_not_specified_not_unfiltered(self, profile):
        l1_scope = [
            self._judgment("preparing for interview backend engineer", "irrelevant"),
            self._judgment("casually looking for frontend", "irrelevant"),
            self._judgment("senior backend, Mumbai", "irrelevant"),
        ]
        assert _format_learning_context(profile, l1_scope=l1_scope) == "Not specified"

    def test_uncertain_is_included_pending_ask_user_flow(self, profile):
        """Interim policy: "uncertain" is included, not dropped — there's no
        ask-the-user resolution mechanism built yet (see l1_scope.py), so
        silently excluding an uncertain item would be indistinguishable
        from confidently judging it irrelevant, which it explicitly isn't.
        """
        l1_scope = [
            self._judgment("preparing for interview backend engineer", "uncertain"),
            self._judgment("casually looking for frontend", "irrelevant"),
            self._judgment("senior backend, Mumbai", "irrelevant"),
        ]
        result = _format_learning_context(profile, l1_scope=l1_scope)
        assert "preparing for interview backend engineer" in result


class TestFormatTaughtConcepts:
    """TS-1: episodic memory of specific things taught in this topic."""

    def test_empty_or_none_shows_placeholder(self):
        assert _format_taught_concepts(None) == "(nothing recorded yet)"
        assert _format_taught_concepts([]) == "(nothing recorded yet)"

    def test_formats_as_bullet_list(self):
        result = _format_taught_concepts(["Signed URLs in CloudFront", "Signed Cookies in CloudFront"])
        assert result == "- Signed URLs in CloudFront\n- Signed Cookies in CloudFront"


class TestFormatStyleNotes:
    """Issue #14: the user's 'how to teach me' note, served via the
    get_user_profile tool (topic_chat_service._execute_loop_tool) rather
    than injected into every system prompt."""

    def test_formats_as_bullet_list(self):
        result = _format_style_notes(
            [{"category": "communication", "note": "Use code examples, be concise"}]
        )
        assert result == "- [communication] Use code examples, be concise"

    def test_empty_shows_placeholder(self):
        assert _format_style_notes([]) == "(none observed yet)"


class TestFormatSubtopicMastery:
    """Per-subtopic mastery, served via the get_skill_state tool rather than
    injected into every system prompt."""

    def test_formats_sorted_weakest_first(self):
        result = _format_subtopic_mastery({"CAP theorem": 55, "Sharding": 20})
        assert result == "- Sharding: 20%\n- CAP theorem: 55%"

    def test_empty_or_none_shows_placeholder(self):
        assert _format_subtopic_mastery(None) == "(not assessed yet)"
        assert _format_subtopic_mastery({}) == "(not assessed yet)"


class TestAttemptFirstTeaching:
    """Issue #12/#50: whether to withhold the answer is decided per-mode (by
    the router), not by one blanket static rule — DIRECT must be exempt from
    the "make them attempt first" framing, or it defeats its own purpose."""

    def test_no_blanket_attempt_first_rule(self):
        """The old universal "do not hand over the full answer" static rule
        is gone — mode-specific instructions are the authority now."""
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("socratic", context)
        assert "do not hand over the full answer" not in result.lower()

    def test_direct_mode_has_no_attempt_first_framing(self):
        """DIRECT must answer immediately — the static block explicitly
        carves it out from the gradual-reveal framing."""
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("direct", context)
        assert "answer immediately" in result.lower()
        assert "no leading question" in result.lower()

    def test_socratic_hint_guided_reference_skill_state_tool(self):
        """No mastery level is injected directly anymore — the mentor calls
        get_skill_state on demand instead (see mentor_v1.md)."""
        context = {"profile": {}, "skill": {}, "episodes": []}
        for mode in ("socratic", "hint", "guided"):
            result = get_system_prompt(mode, context)
            assert "get_skill_state" in result, mode
        assert "leading question" in get_system_prompt("socratic", context).lower()


class TestGetOnboardingPrompt:
    """Tests for get_onboarding_prompt function."""

    def test_returns_string(self):
        result = get_onboarding_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_onboarding_instructions(self):
        result = get_onboarding_prompt()
        assert "onboarding" in result.lower()
        assert "situation summary" in result.lower()
        assert "focus areas" in result.lower()

    def test_contains_suggestion_chips_instruction(self):
        result = get_onboarding_prompt()
        assert "suggestions" in result

    def test_contains_onboarding_complete_instruction(self):
        result = get_onboarding_prompt()
        assert "onboarding_complete" in result


class TestFormatSummaryBlocks:
    """Tests for this topic's own SummaryBlocks — no truncation, oldest first
    (session-narrative-summary spec, Requirement 7.1, 7.2)."""

    def test_empty_blocks(self):
        result = _format_summary_blocks(None)
        assert "no prior sessions" in result.lower()

    def test_not_truncated_at_500_words(self):
        long_text = "word " * 500
        blocks = [{
            "blockId": "b1", "text": long_text, "wordCount": 500,
            "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }]
        result = _format_summary_blocks(blocks)
        assert result.strip() == long_text.strip()
        assert "…" not in result

    def test_oldest_first(self):
        blocks = [
            {"blockId": "b2", "text": "second", "createdAt": datetime(2025, 1, 2, tzinfo=timezone.utc)},
            {"blockId": "b1", "text": "first", "createdAt": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        ]
        result = _format_summary_blocks(blocks)
        assert result.index("first") < result.index("second")


class TestInterpolate:
    """Tests for the template interpolation helper."""

    def test_replaces_known_variables(self):
        result = _interpolate("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_replaces_multiple_variables(self):
        result = _interpolate("{{a}} and {{b}}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_missing_variable_becomes_empty(self):
        result = _interpolate("Hello {{missing}}", {})
        assert result == "Hello "

    def test_no_placeholders_returns_unchanged(self):
        template = "No variables here"
        result = _interpolate(template, {"unused": "value"})
        assert result == template
