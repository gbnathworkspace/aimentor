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
        result = get_system_prompt("topic", context)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_interpolates_profile_fields(self):
        context = {
            "profile": {
                "goal": "Crack FAANG",
                "deadline": "2025-06-01",
                "overall_level": "intermediate",
                "daily_availability": "3 hrs/day",
            },
            "skill": {},
            "episodes": [],
        }
        result = get_system_prompt("planning", context)
        assert "Crack FAANG" in result
        assert "2025-06-01" in result
        assert "intermediate" in result
        assert "3 hrs/day" in result

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
        result = get_system_prompt("topic", context)
        assert "System Design" in result
        assert "advanced" in result
        assert "intermediate" in result
        assert "40%" in result

    def test_includes_mode_instructions_planning(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("planning", context)
        assert "PLANNING mode" in result
        assert "study plan" in result

    def test_includes_mode_instructions_topic(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        result = get_system_prompt("topic", context)
        assert "TOPIC mode" in result
        assert "teach" in result

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
        result = get_system_prompt("topic", context)
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
        result = get_system_prompt("topic", context)
        assert "Arrays session" in result
        assert "two-pointer" in result

    def test_uses_topic_from_context_when_skill_missing(self):
        context = {
            "profile": {},
            "skill": {},
            "episodes": [],
            "topic": "Graphs",
        }
        result = get_system_prompt("topic", context)
        assert "Graphs" in result

    def test_tone_instructions_injected(self):
        context = {"profile": {}, "skill": {}, "episodes": []}
        assert "TOUGH" in get_system_prompt("topic", context, "tough")
        assert "ENCOURAGING" in get_system_prompt("topic", context, "encouraging")

    def test_tone_defaults_to_balanced(self):
        # No tone arg → balanced voice, and the placeholder is always filled.
        result = get_system_prompt("topic", context={"profile": {}, "skill": {}, "episodes": []})
        assert "BALANCED" in result
        assert "{{tone_instructions}}" not in result


class TestGetOnboardingPrompt:
    """Tests for get_onboarding_prompt function."""

    def test_returns_string(self):
        result = get_onboarding_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_onboarding_instructions(self):
        result = get_onboarding_prompt()
        assert "onboarding" in result.lower()
        assert "goal" in result.lower()
        assert "deadline" in result.lower()

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
