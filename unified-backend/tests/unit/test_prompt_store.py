"""Unit tests for the prompt store service."""

import pytest

from app.services.prompt_store import (
    clear_cache,
    get_onboarding_prompt,
    get_system_prompt,
    _format_episodes,
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

    def test_interpolates_profile_fields(self):
        context = {
            "profile": {
                "learning_context": "job_interview",
                "learning_context_detail": {"label": "Crack FAANG"},
                "focus_areas": ["System Design", "DSA"],
                "explanation_style": "answer-first",
                "challenge_tolerance": "high",
                "feedback_tone": "direct",
            },
            "skill": {},
            "episodes": [],
        }
        result = get_system_prompt("planning", context)
        assert "job_interview" in result
        assert "Crack FAANG" in result
        assert "System Design, DSA" in result
        assert "answer-first" in result
        assert "high" in result
        assert "direct" in result

    def test_injects_every_context_and_situation(self):
        """No entry is "active" — all of them reach the prompt."""
        context = {
            "profile": {
                "learning_context": "job_interview",
                "learning_context_detail": {
                    "contexts": ["job_interview", "competitive_test"],
                    "label": "interviewing for staff roles",
                    "situations": [
                        "interviewing for staff roles",
                        "leading the backend rewrite",
                    ],
                },
            },
            "skill": {},
            "episodes": [],
        }
        result = get_system_prompt("planning", context)
        assert "job_interview, competitive_test" in result
        assert "leading the backend rewrite" in result
        # `label` duplicates situations[0] — injected once, not twice
        assert result.count("interviewing for staff roles") == 1

    def test_interpolates_skill_fields(self):
        context = {
            "profile": {},
            "skill": {
                "topic": "System Design",
                "required_level": "advanced",
                "current_level": "intermediate",
                "gap": "40%",
            },
            "episodes": [],
        }
        result = get_system_prompt("socratic", context)
        assert "System Design" in result
        assert "advanced" in result
        assert "intermediate" in result
        assert "40%" in result

    def test_includes_mode_instructions_planning(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("planning", context)
        assert "PLANNING mode" in result
        assert "study plan" in result

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

    def test_includes_mode_instructions_doubt(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("doubt", context)
        assert "DOUBT mode" in result
        assert "doubt" in result.lower()

    def test_includes_mode_instructions_evaluation(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("evaluation", context)
        assert "EVALUATION mode" in result
        assert "assess" in result.lower()

    def test_raises_for_unknown_mode(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        with pytest.raises(ValueError, match="Unknown mode"):
            get_system_prompt("unknown_mode", context)

    def test_handles_missing_profile_gracefully(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("socratic", context)
        assert "Not specified" in result

    def test_includes_episodes_in_prompt(self):
        context = {
            "profile": {},
            "skill": {},
            "episodes": [
                {
                    "title": "Arrays session",
                    "summary": "Covered array basics and two-pointer technique",
                    "topic": "Arrays",
                    "date": "2025-01-15",
                }
            ],
        }
        result = get_system_prompt("socratic", context)
        assert "Arrays session" in result
        assert "two-pointer" in result

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


class TestStyleNotes:
    """Issue #14: the user's 'how to teach me' note reaches the prompt."""

    def test_style_notes_injected(self):
        context = {
            "profile": {
                "style_notes": [
                    {"category": "communication", "note": "Use code examples, be concise"}
                ]
            },
            "skill": {},
            "episodes": [],
        }
        result = get_system_prompt("socratic", context)
        assert "How to Teach This User" in result
        assert "Use code examples, be concise" in result

    def test_no_style_notes_placeholder(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("socratic", context)
        assert "(none observed yet)" in result
        assert "{{style_notes}}" not in result


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

    def test_socratic_hint_guided_show_current_level(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        for mode in ("socratic", "hint", "guided"):
            result = get_system_prompt(mode, context)
            assert "Current Level" in result, mode
        assert "leading question" in get_system_prompt("socratic", context).lower()

    def test_doubt_mode_still_has_hint_ladder(self):
        """doubt mode's own instructions (untouched by the routing change)
        still carry the fading hint ladder."""
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("doubt", context)
        assert "ladder" in result.lower()
        assert "Current Level" in result

    def test_evaluation_stays_hint_free(self):
        # Evaluation must NOT gain a hint ladder — it withholds hints by design.
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("evaluation", context)
        assert "Do not give hints" in result


class TestUploadedDocuments:
    """Issue #4: ingested file chunks must reach the mentor prompt."""

    def test_documents_injected(self):
        context = {
            "profile": {},
            "skill": {},
            "episodes": [],
            "documents": [
                {"text": "5 years Python at Acme", "metadata": {"filename": "resume.pdf"}},
            ],
        }
        result = get_system_prompt("socratic", context)
        assert "resume.pdf" in result
        assert "5 years Python at Acme" in result
        assert "{{documents}}" not in result

    def test_no_documents_placeholder(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("socratic", context)
        assert "(no uploaded documents)" in result


class TestGetOnboardingPrompt:
    """Tests for get_onboarding_prompt function."""

    def test_returns_string(self):
        result = get_onboarding_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_onboarding_instructions(self):
        result = get_onboarding_prompt()
        assert "onboarding" in result.lower()
        assert "learning context" in result.lower()
        assert "focus areas" in result.lower()

    def test_contains_suggestion_chips_instruction(self):
        result = get_onboarding_prompt()
        assert "suggestions" in result

    def test_contains_onboarding_complete_instruction(self):
        result = get_onboarding_prompt()
        assert "onboarding_complete" in result


class TestFormatEpisodes:
    """Tests for the episode formatting helper."""

    def test_empty_episodes(self):
        result = _format_episodes([])
        assert "no prior sessions" in result.lower()

    def test_single_episode(self):
        episodes = [
            {
                "title": "BFS deep dive",
                "summary": "Covered breadth-first search on graphs",
                "topic": "Graphs",
                "date": "2025-01-10",
            }
        ]
        result = _format_episodes(episodes)
        assert "[1]" in result
        assert "BFS deep dive" in result
        assert "Graphs" in result
        assert "2025-01-10" in result

    def test_multiple_episodes(self):
        episodes = [
            {"title": "Session A", "summary": "Summary A", "topic": "T1", "date": "2025-01-01"},
            {"title": "Session B", "summary": "Summary B", "topic": "T2", "date": "2025-01-02"},
        ]
        result = _format_episodes(episodes)
        assert "[1]" in result
        assert "[2]" in result
        assert "Session A" in result
        assert "Session B" in result

    def test_truncates_long_summaries(self):
        long_summary = "x" * 500
        episodes = [{"title": "Long", "summary": long_summary, "topic": "T", "date": ""}]
        result = _format_episodes(episodes)
        # Should be truncated to ~300 chars + ellipsis
        assert "…" in result
        assert len(result) < 500


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
