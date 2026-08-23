"""Unit tests for app/services/l1_scope.py.

Covers:
- classify_relevance short-circuits (no LLM call) on empty input
- classify_relevance never trusts model-echoed text — position-pairs the
  real input text back in instead (regression for the design-review finding)
- classify_relevance raises on a judgment-count mismatch instead of
  silently mis-zipping
- classify_relevance returns a real three-way verdict (relevant/irrelevant/
  uncertain), not a bool with bias baked in
- extract_situations_and_contexts label-folding / fallback behavior
- compute_profile_stamp stability
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.l1_scope import (
    _Judgment,
    _RelevanceJudgments,
    classify_relevance,
    compute_profile_stamp,
    extract_focus_areas,
    extract_situations_and_contexts,
)


def _judgments(situation_judgments=None, context_judgments=None, focus_area_judgments=None):
    """Build a _RelevanceJudgments response, defaulting unused lists to empty."""
    return _RelevanceJudgments(
        situation_judgments=situation_judgments or [],
        context_judgments=context_judgments or [],
        focus_area_judgments=focus_area_judgments or [],
    )


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
            result = await classify_relevance("React", [], [])
        assert result == []
        mock_cls.assert_not_called()


class TestClassifyRelevanceTextFidelity:
    @pytest.mark.asyncio
    async def test_situation_text_is_position_paired_not_model_echoed(self):
        """The model's structured output carries no text at all — proves
        the returned `situation` field can only have come from our input
        list, never from anything the model produced."""
        situations = ["preparing for interview backend engineer", "casually looking for frontend"]
        contexts = ["senior backend, Mumbai"]
        response = _judgments(
            situation_judgments=[
                _Judgment(verdict="relevant", reason="interview prep is relevant"),
                _Judgment(verdict="irrelevant", reason="not topical"),
            ],
            context_judgments=[_Judgment(verdict="uncertain", reason="could go either way")],
        )
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_relevance("System Design", situations, contexts)

        assert result == [
            {"situation": situations[0], "verdict": "relevant", "reason": "interview prep is relevant"},
            {"situation": situations[1], "verdict": "irrelevant", "reason": "not topical"},
            {"situation": contexts[0], "verdict": "uncertain", "reason": "could go either way"},
        ]

    @pytest.mark.asyncio
    async def test_focus_areas_are_also_position_paired(self):
        focus_areas = ["Enterprise REST API development", "AI/ML integration"]
        response = _judgments(
            focus_area_judgments=[
                _Judgment(verdict="relevant", reason="on topic"),
                _Judgment(verdict="irrelevant", reason="unrelated"),
            ],
        )
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_relevance("React", [], [], focus_areas)

        assert result == [
            {"situation": focus_areas[0], "verdict": "relevant", "reason": "on topic"},
            {"situation": focus_areas[1], "verdict": "irrelevant", "reason": "unrelated"},
        ]

    @pytest.mark.asyncio
    async def test_raises_on_situation_judgment_count_mismatch(self):
        response = _judgments(
            situation_judgments=[_Judgment(verdict="relevant", reason="x")],  # only 1, but 2 given
        )
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            with pytest.raises(ValueError, match="count mismatch"):
                await classify_relevance("React", ["a", "b"], [])

    @pytest.mark.asyncio
    async def test_raises_on_context_judgment_count_mismatch(self):
        response = _judgments(
            context_judgments=[_Judgment(verdict="relevant", reason="x"), _Judgment(verdict="irrelevant", reason="y")],
        )
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            with pytest.raises(ValueError, match="count mismatch"):
                await classify_relevance("React", [], ["only one context"])

    @pytest.mark.asyncio
    async def test_raises_on_focus_area_judgment_count_mismatch(self):
        response = _judgments()  # 0 focus_area_judgments, but 1 given
        with patch("app.services.l1_scope.ChatAnthropic", _mock_chat_anthropic(response)):
            with pytest.raises(ValueError, match="count mismatch"):
                await classify_relevance("React", [], [], ["one focus area"])


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
            await classify_relevance("React", ["a"], [])

        sent_prompt = " ".join(mock_structured.ainvoke.call_args[0][0].split())
        assert "'relevant', 'irrelevant', or 'uncertain'" in sent_prompt


class TestExtractFocusAreas:
    def test_returns_focus_areas_list(self):
        assert extract_focus_areas({"focus_areas": ["a", "b"]}) == ["a", "b"]

    def test_missing_field_returns_empty_list(self):
        assert extract_focus_areas({}) == []


class TestExtractSituationsAndContexts:
    def test_folds_label_into_situations_when_absent(self):
        profile = {"learning_context_detail": {"situations": ["b"], "contexts": ["c"], "label": "a"}}
        situations, contexts = extract_situations_and_contexts(profile)
        assert situations == ["a", "b"]
        assert contexts == ["c"]

    def test_does_not_duplicate_label_already_present(self):
        profile = {"learning_context_detail": {"situations": ["a", "b"], "label": "a"}}
        situations, _ = extract_situations_and_contexts(profile)
        assert situations == ["a", "b"]

    def test_falls_back_to_learning_context_when_contexts_empty(self):
        profile = {"learning_context": "job_interview", "learning_context_detail": {}}
        _, contexts = extract_situations_and_contexts(profile)
        assert contexts == ["job_interview"]

    def test_empty_profile_returns_empty_lists(self):
        assert extract_situations_and_contexts({}) == ([], [])


class TestComputeProfileStamp:
    def test_stable_for_identical_input(self):
        s1 = compute_profile_stamp(["a", "b"], ["c"], ["d"])
        s2 = compute_profile_stamp(["a", "b"], ["c"], ["d"])
        assert s1 == s2

    def test_changes_when_situations_change(self):
        s1 = compute_profile_stamp(["a"], ["c"], [])
        s2 = compute_profile_stamp(["a", "b"], ["c"], [])
        assert s1 != s2

    def test_changes_when_contexts_change(self):
        s1 = compute_profile_stamp(["a"], ["c"], [])
        s2 = compute_profile_stamp(["a"], ["c", "d"], [])
        assert s1 != s2

    def test_changes_when_focus_areas_change(self):
        s1 = compute_profile_stamp(["a"], ["c"], ["d"])
        s2 = compute_profile_stamp(["a"], ["c"], ["d", "e"])
        assert s1 != s2
