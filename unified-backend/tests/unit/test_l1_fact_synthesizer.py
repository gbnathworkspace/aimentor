"""Unit tests for app/services/l1_fact_synthesizer.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from app.models.document_upload import L1SynthesisOutput, SynthesizedStyleNote
from app.models.profile import ProposableField, StyleNoteCategory
from app.services.l1_fact_synthesizer import (
    SynthesisResult,
    _build_proposals,
    _validate_focus_areas,
    _validate_style_notes,
    synthesize_l1_facts,
    truncate_to_token_limit,
)


class TestTruncateToTokenLimit:
    """Tests for token-based truncation at sentence boundary."""

    def test_short_text_not_truncated(self):
        text = "Hello world. This is short."
        result = truncate_to_token_limit(text, max_tokens=100)
        assert result == text

    def test_empty_text(self):
        assert truncate_to_token_limit("", max_tokens=100) == ""

    def test_truncation_at_sentence_boundary(self):
        # Build text that exceeds token limit
        sentences = [f"This is sentence number {i}." for i in range(500)]
        text = " ".join(sentences)
        result = truncate_to_token_limit(text, max_tokens=50)
        # Result should end at a sentence boundary (period followed by space or end)
        assert result.rstrip().endswith(".")
        # Result should be shorter than original
        assert len(result) < len(text)

    def test_truncation_respects_question_marks(self):
        sentences = ["Is this a question? " * 200]
        text = "".join(sentences)
        result = truncate_to_token_limit(text, max_tokens=20)
        assert "?" in result

    def test_no_sentence_boundary_returns_truncated(self):
        # Text with no sentence boundaries
        text = "word " * 5000
        result = truncate_to_token_limit(text, max_tokens=10)
        assert len(result) > 0
        assert len(result) < len(text)


class TestValidateStyleNotes:
    """Tests for style note validation."""

    def test_valid_style_note(self):
        notes = [
            {
                "category": "motivation",
                "note": "Responds well to real-world examples",
                "source_quote": "I learn best from practical projects",
            }
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 1
        assert result[0].category == StyleNoteCategory.MOTIVATION
        assert result[0].note == "Responds well to real-world examples"
        assert result[0].source_quote == "I learn best from practical projects"

    def test_source_quote_exceeds_200_chars_discarded(self):
        notes = [
            {
                "category": "pacing",
                "note": "Short note",
                "source_quote": "x" * 201,
            }
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 0

    def test_source_quote_exactly_200_chars_accepted(self):
        notes = [
            {
                "category": "pacing",
                "note": "Short note",
                "source_quote": "x" * 200,
            }
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 1

    def test_missing_source_quote_discarded(self):
        notes = [{"category": "pacing", "note": "Some note", "source_quote": ""}]
        result = _validate_style_notes(notes)
        assert len(result) == 0

    def test_note_exceeds_140_chars_discarded(self):
        notes = [
            {
                "category": "communication",
                "note": "n" * 141,
                "source_quote": "valid quote",
            }
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 0

    def test_note_exactly_140_chars_accepted(self):
        notes = [
            {
                "category": "communication",
                "note": "n" * 140,
                "source_quote": "valid quote",
            }
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 1

    def test_invalid_category_discarded(self):
        notes = [
            {
                "category": "nonexistent",
                "note": "Some note",
                "source_quote": "some quote",
            }
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 0

    def test_mixed_valid_and_invalid(self):
        notes = [
            {
                "category": "pacing",
                "note": "Valid note",
                "source_quote": "Valid quote",
            },
            {
                "category": "invalid_cat",
                "note": "Should be discarded",
                "source_quote": "quote",
            },
            {
                "category": "context",
                "note": "Also valid",
                "source_quote": "Another quote",
            },
        ]
        result = _validate_style_notes(notes)
        assert len(result) == 2
        assert result[0].category == StyleNoteCategory.PACING
        assert result[1].category == StyleNoteCategory.CONTEXT


class TestValidateFocusAreas:
    """Tests for focus area validation."""

    def test_valid_focus_areas(self):
        areas = ["System Design", "Dynamic Programming", "SQL Optimization"]
        result = _validate_focus_areas(areas)
        assert result == areas

    def test_exceeds_60_chars_discarded(self):
        areas = ["Short", "x" * 61, "Also valid"]
        result = _validate_focus_areas(areas)
        assert result == ["Short", "Also valid"]

    def test_exactly_60_chars_accepted(self):
        areas = ["x" * 60]
        result = _validate_focus_areas(areas)
        assert len(result) == 1

    def test_empty_string_discarded(self):
        areas = ["Valid", "", "Also valid"]
        result = _validate_focus_areas(areas)
        assert result == ["Valid", "Also valid"]

    def test_empty_list(self):
        result = _validate_focus_areas([])
        assert result == []


class TestBuildProposals:
    """Tests for building PendingProfileChange-shaped proposals."""

    def test_style_notes_proposals(self):
        output = L1SynthesisOutput(
            style_notes=[
                SynthesizedStyleNote(
                    category=StyleNoteCategory.MOTIVATION,
                    note="Learns well from projects",
                    source_quote="I prefer hands-on projects",
                )
            ],
        )
        proposals = _build_proposals(output, "job-1")
        assert len(proposals) == 1
        assert proposals[0]["field"] == ProposableField.STYLE_NOTE.value
        assert proposals[0]["proposed_value"]["category"] == "motivation"
        assert proposals[0]["proposed_value"]["source_quote"] == "I prefer hands-on projects"

    def test_focus_area_proposals(self):
        output = L1SynthesisOutput(
            focus_areas=["System Design", "Distributed Systems"],
        )
        proposals = _build_proposals(output, "job-1")
        assert len(proposals) == 2
        assert proposals[0]["field"] == ProposableField.FOCUS_AREA.value
        assert proposals[0]["proposed_value"] == {"value": "System Design"}
        assert proposals[1]["proposed_value"] == {"value": "Distributed Systems"}

    def test_empty_output_no_proposals(self):
        output = L1SynthesisOutput()
        proposals = _build_proposals(output, "job-1")
        assert proposals == []

    def test_combined_proposals(self):
        output = L1SynthesisOutput(
            focus_areas=["API Design"],
            style_notes=[
                SynthesizedStyleNote(
                    category=StyleNoteCategory.PACING,
                    note="Prefers fast pace",
                    source_quote="Let's move quickly",
                )
            ],
        )
        proposals = _build_proposals(output, "job-1")
        assert len(proposals) == 2
        fields = [p["field"] for p in proposals]
        assert ProposableField.STYLE_NOTE.value in fields
        assert ProposableField.FOCUS_AREA.value in fields


class TestSynthesizeL1Facts:
    """Tests for the main synthesize_l1_facts function."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_success(self):
        result = await synthesize_l1_facts("", "user-1", "job-1")
        assert result.success is True
        assert result.proposals == []
        assert result.error is None

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty_success(self):
        result = await synthesize_l1_facts("   \n\t  ", "user-1", "job-1")
        assert result.success is True
        assert result.proposals == []

    @pytest.mark.asyncio
    async def test_llm_returns_valid_json(self):
        """Mocking the LLM call to return valid proposals."""
        llm_response = json.dumps({
            "focus_areas": ["Backend Development", "System Design"],
        })

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = llm_response
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.accumulate_proposals", new_callable=AsyncMock) as mock_accum:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client
            # accumulate_proposals returns proposals unchanged
            mock_accum.side_effect = lambda proposals, user_id: proposals

            result = await synthesize_l1_facts(
                "I am a senior backend developer preparing for system design interviews.",
                "user-1",
                "job-1",
            )

        assert result.success is True
        assert result.error is None
        assert len(result.proposals) == 2  # 2 focus_areas

    @pytest.mark.asyncio
    async def test_llm_returns_empty_json(self):
        """LLM returns {} when nothing relevant is found."""
        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "{}"
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Random text with no profile relevance.",
                "user-1",
                "job-1",
            )

        assert result.success is True
        assert result.proposals == []

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self):
        """LLM returns non-JSON text — no retry (not an LLM call failure)."""
        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "This is not valid JSON at all"
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Some text.",
                "user-1",
                "job-1",
            )

        assert result.success is False
        assert "not valid JSON" in result.error
        assert result.proposals == []

    @pytest.mark.asyncio
    async def test_llm_call_failure(self):
        """LLM call fails on both attempts (initial + retry)."""
        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API timeout")
            )
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Some document text.",
                "user-1",
                "job-1",
            )

        assert result.success is False
        assert "LLM call failed after retry" in result.error
        assert result.proposals == []
        # Verify retry delay was applied
        mock_sleep.assert_called_once_with(2)
        # Verify LLM was called exactly twice (initial + retry)
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_llm_call_succeeds_on_retry(self):
        """LLM call fails first time but succeeds on retry."""
        llm_response = json.dumps({"focus_areas": ["System Design"]})

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = llm_response
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("app.services.l1_fact_synthesizer.accumulate_proposals", new_callable=AsyncMock) as mock_accum:
            mock_client = AsyncMock()
            # First call raises, second call succeeds
            mock_client.messages.create = AsyncMock(
                side_effect=[Exception("Rate limited"), mock_message]
            )
            mock_client_cls.return_value = mock_client
            mock_accum.side_effect = lambda proposals, user_id: proposals

            result = await synthesize_l1_facts(
                "I want to learn system design.",
                "user-1",
                "job-1",
            )

        assert result.success is True
        assert result.error is None
        assert len(result.proposals) == 1
        assert result.proposals[0]["proposed_value"] == {"value": "System Design"}
        # Verify retry delay was applied
        mock_sleep.assert_called_once_with(2)
        # Verify LLM was called exactly twice
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_llm_call_succeeds_on_first_try_no_retry(self):
        """LLM call succeeds on first attempt — no retry or delay."""
        llm_response = json.dumps({"focus_areas": ["Python"]})

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = llm_response
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             patch("app.services.l1_fact_synthesizer.accumulate_proposals", new_callable=AsyncMock) as mock_accum:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client
            mock_accum.side_effect = lambda proposals, user_id: proposals

            result = await synthesize_l1_facts(
                "I want to learn Python.",
                "user-1",
                "job-1",
            )

        assert result.success is True
        assert len(result.proposals) == 1
        # Verify no retry delay occurred
        mock_sleep.assert_not_called()
        # Verify LLM was called exactly once
        assert mock_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_no_actionable_proposals_returns_done(self):
        """LLM returns valid JSON with no proposals — marked as done (success=True, empty proposals)."""
        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "{}"
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Some unrelated text about cooking recipes.",
                "user-1",
                "job-1",
            )

        # Requirement 4.7: No proposals → success=True (job should be marked "done")
        assert result.success is True
        assert result.proposals == []
        assert result.error is None

    @pytest.mark.asyncio
    async def test_llm_schema_failure_discards_proposals(self):
        """LLM returns JSON that doesn't match schema — discards proposals, marks failed (Req 4.9)."""
        bad_response = json.dumps({
            "style_notes": "not_a_list",
        })

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = bad_response
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Some text.",
                "user-1",
                "job-1",
            )

        # Requirement 4.9: Schema failure → proposals discarded, marked failed
        assert result.success is False
        assert "schema" in result.error.lower()
        assert result.proposals == []

    @pytest.mark.asyncio
    async def test_llm_timeout_error_triggers_retry(self):
        """Specific timeout errors trigger the retry mechanism."""
        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=anthropic.APITimeoutError(request=MagicMock())
            )
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Some document text.",
                "user-1",
                "job-1",
            )

        assert result.success is False
        assert "APITimeoutError" in result.error
        mock_sleep.assert_called_once_with(2)
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_llm_rate_limit_error_triggers_retry(self):
        """Rate limit errors trigger the retry mechanism."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=anthropic.RateLimitError(
                    message="Rate limit exceeded",
                    response=mock_response,
                    body=None,
                )
            )
            mock_client_cls.return_value = mock_client

            result = await synthesize_l1_facts(
                "Some document text.",
                "user-1",
                "job-1",
            )

        assert result.success is False
        assert "RateLimitError" in result.error
        mock_sleep.assert_called_once_with(2)
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_llm_returns_code_fenced_json(self):
        """LLM wraps JSON in markdown code fences — should still parse."""
        llm_response = '```json\n{"focus_areas": ["Python"]}\n```'

        mock_message = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = llm_response
        mock_message.content = [mock_text_block]

        with patch("app.services.l1_fact_synthesizer.anthropic.AsyncAnthropic") as mock_client_cls, \
             patch("app.services.l1_fact_synthesizer.accumulate_proposals", new_callable=AsyncMock) as mock_accum:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_message)
            mock_client_cls.return_value = mock_client
            mock_accum.side_effect = lambda proposals, user_id: proposals

            result = await synthesize_l1_facts(
                "I want to learn Python.",
                "user-1",
                "job-1",
            )

        assert result.success is True
        assert len(result.proposals) == 1
        assert result.proposals[0]["proposed_value"] == {"value": "Python"}

