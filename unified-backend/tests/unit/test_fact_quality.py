"""Unit tests for app/services/fact_quality.py.

Covers:
- classify_fact_quality short-circuits (no LLM call) on empty input
- classify_fact_quality position-pairs the real input text back in
- classify_fact_quality raises on a judgment-count mismatch
- classify_fact_quality normalizes a no-op rewrite (identical to the
  original text) to is_fact=True instead of leaving an unfixable
  "Rewrite as a fact" button that can never clear
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.fact_quality import _FactJudgment, _FactJudgments, classify_fact_quality


def _mock_chat_anthropic(response: _FactJudgments):
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=response)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    return MagicMock(return_value=mock_llm)


class TestClassifyFactQualityEmptyInput:
    @pytest.mark.asyncio
    async def test_returns_empty_list_without_llm_call(self):
        with patch("app.services.fact_quality.ChatAnthropic") as mock_cls:
            result = await classify_fact_quality([])
        assert result == []
        mock_cls.assert_not_called()


class TestClassifyFactQualityTextFidelity:
    @pytest.mark.asyncio
    async def test_text_is_position_paired_not_model_echoed(self):
        texts = ["I am a backend engineer", "Cloud architecture"]
        response = _FactJudgments(judgments=[
            _FactJudgment(is_fact=True, reason="states the user's role"),
            _FactJudgment(is_fact=False, reason="names a topic, not a fact", rewrite="I have experience with cloud architecture"),
        ])
        with patch("app.services.fact_quality.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_fact_quality(texts)

        assert result == [
            {"text": texts[0], "is_fact": True, "reason": "states the user's role", "rewrite": None},
            {
                "text": texts[1], "is_fact": False, "reason": "names a topic, not a fact",
                "rewrite": "I have experience with cloud architecture",
            },
        ]

    @pytest.mark.asyncio
    async def test_raises_on_judgment_count_mismatch(self):
        response = _FactJudgments(judgments=[_FactJudgment(is_fact=True, reason="x")])
        with patch("app.services.fact_quality.ChatAnthropic", _mock_chat_anthropic(response)):
            with pytest.raises(ValueError, match="count mismatch"):
                await classify_fact_quality(["a", "b"])


class TestClassifyFactQualityNoOpRewrite:
    @pytest.mark.asyncio
    async def test_rewrite_identical_to_text_flips_to_is_fact_true(self):
        """A rewrite equal to the original text can never fix anything —
        clicking "Rewrite as a fact" would be a no-op and the warning
        could never clear. Treat it as already as good as it gets."""
        text = "I am interested in learning React"
        response = _FactJudgments(judgments=[
            _FactJudgment(is_fact=False, reason="reads like a topic", rewrite=text),
        ])
        with patch("app.services.fact_quality.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_fact_quality([text])

        assert result == [{"text": text, "is_fact": True, "reason": "reads like a topic", "rewrite": None}]

    @pytest.mark.asyncio
    async def test_missing_rewrite_on_is_fact_false_flips_to_true(self):
        text = "Something ambiguous"
        response = _FactJudgments(judgments=[
            _FactJudgment(is_fact=False, reason="unsure", rewrite=None),
        ])
        with patch("app.services.fact_quality.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_fact_quality([text])

        assert result[0]["is_fact"] is True
        assert result[0]["rewrite"] is None

    @pytest.mark.asyncio
    async def test_case_and_whitespace_insensitive_noop_check(self):
        text = "I am interested in React"
        response = _FactJudgments(judgments=[
            _FactJudgment(is_fact=False, reason="x", rewrite="  i am interested in react  "),
        ])
        with patch("app.services.fact_quality.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_fact_quality([text])

        assert result[0]["is_fact"] is True

    @pytest.mark.asyncio
    async def test_genuinely_different_rewrite_is_kept(self):
        text = "Cloud architecture"
        rewrite = "I have experience with cloud architecture"
        response = _FactJudgments(judgments=[
            _FactJudgment(is_fact=False, reason="bare topic", rewrite=rewrite),
        ])
        with patch("app.services.fact_quality.ChatAnthropic", _mock_chat_anthropic(response)):
            result = await classify_fact_quality([text])

        assert result[0]["is_fact"] is False
        assert result[0]["rewrite"] == rewrite
