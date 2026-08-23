"""Unit tests for app/services/l1_scope.py.

Covers:
- classify_relevance short-circuits (no LLM call) on empty input
- classify_relevance never trusts model-echoed text — position-pairs the
  real input text back in instead (regression for the design-review finding)
- classify_relevance raises on a judgment-count mismatch instead of
  silently mis-zipping
- classify_relevance returns a real three-way verdict (relevant/irrelevant/
  uncertain), not a bool with bias baked in
- extract_situations label-folding / fallback behavior
- compute_profile_stamp stability
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.l1_scope import (
    _Judgment,
    _RelevanceJudgments,
    classify_relevance,
    compute_profile_stamp,
    extract_situations,
)


def _judgments(situation_judgments=None):
    """Build a _RelevanceJudgments response, defaulting to empty."""
    return _RelevanceJudgments(situation_judgments=situation_judgments or [])


def _mock_chat_anthropic(response: _RelevanceJudgments):
    """Patch target for ChatAnthropic().with_structured_output(...).ainvoke(...)."""
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=response)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    return MagicMock(return_value=mock_llm)


class TestClassifyRelevanceEmptyInput:
    @pytest.mark.asyncio
    async def test_returns_empty_list_without_llm_call(self):
        with patch("app.services.l1_scope.ChatAnthropic") as mock_cls:
            result = await classify_relevance("React", [])
        assert result == []
        mock_cls.assert_not_called()


class TestClassifyRelevanceTextFidelity:
    @pytest.mark.asyncio
    async def test_situation_text_is_position_paired_not_model_echoed(self):
        """The model's structured output carries no text at all — proves
        the returned `situation` field can only have come from our input
        list, never from anything the model produced."""
        situations = ["preparing for interview backend engineer", "casually looking for frontend"]
        response = _judgments(
            situation_judgments=[
                _Judgment(verdict="relevant", reason="interview prep is relevant"),
                _Judgment(verdict="irrelevant", reason="not topical"),
            ],
        )
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_relevance("System Design", situations)

        assert result == [
            {"situation": situations[0], "verdict": "relevant", "reason": "interview prep is relevant"},
            {"situation": situations[1], "verdict": "irrelevant", "reason": "not topical"},
        ]

    @pytest.mark.asyncio
    async def test_raises_on_situation_judgment_count_mismatch(self):
        response = _judgments(
            situation_judgments=[_Judgment(verdict="relevant", reason="x")],  # only 1, but 2 given
        )
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            with pytest.raises(ValueError, match="count mismatch"):
                await classify_relevance("React", ["a", "b"])


class TestClassifyRelevancePromptAsksThreeWay:
    @pytest.mark.asyncio
    async def test_prompt_offers_uncertain_as_a_real_option(self):
        """Uncertain must be a genuine third outcome the model can pick,
        not a bias folded into a boolean judgment."""
        response = _judgments(situation_judgments=[_Judgment(verdict="relevant", reason="x")])
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured
        with patch("app.services.l1_scope.ChatAnthropic", MagicMock(return_value=mock_llm)):
            await classify_relevance("React", ["a"])

        sent_prompt = " ".join(mock_structured.ainvoke.call_args[0][0].split())
        assert "'relevant', 'irrelevant', or 'uncertain'" in sent_prompt


class TestExtractSituations:
    def test_folds_label_into_situations_when_absent(self):
        profile = {"learning_context_detail": {"situations": ["b"], "label": "a"}}
        situations = extract_situations(profile)
        assert situations == ["a", "b"]

    def test_does_not_duplicate_label_already_present(self):
        profile = {"learning_context_detail": {"situations": ["a", "b"], "label": "a"}}
        situations = extract_situations(profile)
        assert situations == ["a", "b"]

    def test_folds_in_learning_context_when_not_already_present(self):
        profile = {"learning_context": "job_interview", "learning_context_detail": {"situations": ["a"]}}
        situations = extract_situations(profile)
        assert situations == ["a", "job_interview"]

    def test_does_not_duplicate_learning_context_already_present(self):
        profile = {"learning_context": "job_interview", "learning_context_detail": {"situations": ["job_interview"]}}
        situations = extract_situations(profile)
        assert situations == ["job_interview"]

    def test_empty_profile_returns_empty_list(self):
        assert extract_situations({}) == []


class TestComputeProfileStamp:
    def test_stable_for_identical_input(self):
        s1 = compute_profile_stamp(["a", "b"])
        s2 = compute_profile_stamp(["a", "b"])
        assert s1 == s2

    def test_changes_when_situations_change(self):
        s1 = compute_profile_stamp(["a"])
        s2 = compute_profile_stamp(["a", "b"])
        assert s1 != s2
