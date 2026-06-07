"""Unit tests for the onboarding router."""

import pytest

from app.routers.onboarding import parse_onboarding_response


class TestParseOnboardingResponse:
    """Tests for parse_onboarding_response function."""

    def test_extracts_suggestions_block(self):
        """Should extract JSON array from suggestions fenced block."""
        text = (
            "What's your learning goal?\n\n"
            '```json suggestions\n["Learn Python", "Crack FAANG", "System Design"]\n```'
        )
        result = parse_onboarding_response(text)
        assert result["suggestions"] == ["Learn Python", "Crack FAANG", "System Design"]
        assert result["complete"] is False
        assert result["profile_data"] is None

    def test_extracts_onboarding_complete_block(self):
        """Should extract profile data from onboarding_complete fenced block."""
        text = (
            "Great, I've got everything I need!\n\n"
            "```json onboarding_complete\n"
            '{"goal": "crack FAANG interviews", "deadline": "3 months", '
            '"overall_level": "intermediate", "daily_availability": "2 hours"}\n'
            "```"
        )
        result = parse_onboarding_response(text)
        assert result["complete"] is True
        assert result["profile_data"] == {
            "goal": "crack FAANG interviews",
            "deadline": "3 months",
            "overall_level": "intermediate",
            "daily_availability": "2 hours",
        }

    def test_extracts_both_suggestions_and_complete(self):
        """Should handle both blocks in the same response."""
        text = (
            "Perfect! Here's your profile.\n\n"
            '```json suggestions\n["Start now", "Adjust plan"]\n```\n\n'
            "```json onboarding_complete\n"
            '{"goal": "learn ML", "deadline": "6 months", '
            '"overall_level": "beginner", "daily_availability": "1 hour"}\n'
            "```"
        )
        result = parse_onboarding_response(text)
        assert result["suggestions"] == ["Start now", "Adjust plan"]
        assert result["complete"] is True
        assert result["profile_data"]["goal"] == "learn ML"

    def test_cleans_text_removes_fenced_blocks(self):
        """Should remove fenced blocks from the text output."""
        text = (
            "Welcome! What would you like to learn?\n\n"
            '```json suggestions\n["Option A", "Option B"]\n```'
        )
        result = parse_onboarding_response(text)
        assert "```json" not in result["text"]
        assert "Welcome! What would you like to learn?" in result["text"]

    def test_handles_invalid_suggestions_json(self):
        """Should return empty suggestions if JSON is malformed."""
        text = "Hello!\n\n```json suggestions\n{not valid json}\n```"
        result = parse_onboarding_response(text)
        assert result["suggestions"] == []

    def test_handles_invalid_complete_json(self):
        """Should not mark complete if JSON is malformed."""
        text = "Done!\n\n```json onboarding_complete\n{broken json\n```"
        result = parse_onboarding_response(text)
        assert result["complete"] is False
        assert result["profile_data"] is None

    def test_handles_no_special_blocks(self):
        """Should return plain text if no fenced blocks are present."""
        text = "Hello! Tell me about your goals."
        result = parse_onboarding_response(text)
        assert result["text"] == "Hello! Tell me about your goals."
        assert result["suggestions"] == []
        assert result["complete"] is False
        assert result["profile_data"] is None

    def test_handles_empty_text(self):
        """Should handle empty string gracefully."""
        result = parse_onboarding_response("")
        assert result["text"] == ""
        assert result["suggestions"] == []
        assert result["complete"] is False
        assert result["profile_data"] is None
