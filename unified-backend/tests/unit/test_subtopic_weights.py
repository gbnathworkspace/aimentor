"""Unit tests for DeriveSubtopicWeights: pure arithmetic plus the LLM-based
mention-counting call (mocked, per the pattern in test_compaction_llm.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.subtopic_weights import (
    NUDGE_CAP,
    apply_nudges,
    derive_subtopic_weights,
    pairwise_wins_to_counts,
    _count_mentions_llm,
    _normalize,
    _parse_json_object,
    _score_proficiency_llm,
)


def _mock_text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_normalize_sums_to_100():
    weights = _normalize({"a": 3, "b": 1})
    assert weights["a"] == pytest.approx(75.0)
    assert weights["b"] == pytest.approx(25.0)
    assert sum(weights.values()) == pytest.approx(100.0)


def test_normalize_zero_counts_splits_evenly():
    weights = _normalize({"a": 0, "b": 0})
    assert weights == {"a": 50.0, "b": 50.0}


def test_parse_json_object_strips_markdown_fence():
    parsed = _parse_json_object('```json\n{"a": 1, "b": 0}\n```')
    assert parsed == {"a": 1, "b": 0}


@pytest.mark.asyncio
async def test_count_mentions_llm_uses_model_counts():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_text_response('{"topic a": 3, "topic b": 0}')
    )

    with patch("app.services.subtopic_weights.anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("app.services.subtopic_weights.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
            counts = await _count_mentions_llm("some evidence text", ["topic a", "topic b"])

    assert counts == {"topic a": 3, "topic b": 0}


@pytest.mark.asyncio
async def test_count_mentions_llm_defaults_missing_subtopic_to_zero():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_text_response('{"topic a": 2}'))

    with patch("app.services.subtopic_weights.anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("app.services.subtopic_weights.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
            counts = await _count_mentions_llm("some evidence text", ["topic a", "topic b"])

    assert counts == {"topic a": 2, "topic b": 0}


def test_pairwise_wins_to_counts():
    comparisons = [("a", "b"), ("a", "c"), ("b", "c")]
    counts = pairwise_wins_to_counts(comparisons)
    assert counts == {"a": 2, "b": 1, "c": 0}


def test_pairwise_wins_to_counts_ignores_stale_subtopics_list():
    # Regression: counts must come entirely from the comparisons themselves,
    # never from an externally supplied subtopics list that might have
    # regenerated with different names since the ranking was captured.
    comparisons = [("a", "b"), ("a", "c"), ("b", "c")]
    counts = pairwise_wins_to_counts(comparisons)
    assert sum(counts.values()) == len(comparisons)
    assert set(counts) == {"a", "b", "c"}


def test_nudge_is_clamped_to_cap():
    baseline = {"a": 50.0, "b": 50.0}
    final, _ = apply_nudges(baseline, {"a": 1000.0})
    # a's raw nudge is clamped to +NUDGE_CAP before renormalizing
    expected_a = (50 + NUDGE_CAP) / (50 + NUDGE_CAP + 50) * 100
    assert final["a"] == pytest.approx(expected_a)
    assert sum(final.values()) == pytest.approx(100.0)


def test_opposed_max_nudges_flag_both():
    baseline = {"a": 50.0, "b": 50.0}
    final, flags = apply_nudges(baseline, {"a": NUDGE_CAP, "b": -NUDGE_CAP})
    assert final["a"] > final["b"]
    flagged = {f.subtopic for f in flags}
    assert flagged == {"a", "b"}


def test_small_nudge_produces_no_flag():
    baseline = {"a": 50.0, "b": 50.0}
    _, flags = apply_nudges(baseline, {"a": 1.0})
    assert flags == []


@pytest.mark.asyncio
async def test_zero_count_subtopic_gets_smoothed_nonzero_weight():
    subtopics = ["a", "b", "c"]
    counts = {"a": 10, "b": 5, "c": 0}
    with patch("app.services.subtopic_weights._count_mentions_llm", AsyncMock(return_value=counts)):
        result = await derive_subtopic_weights(
            topic="Test", goal="job_performance", subtopics=subtopics, work_evidence="evidence"
        )
    assert result.needs_pairwise is False
    assert result.weights is not None
    assert result.weights["c"] > 0  # smoothed — a real subtopic never reads as a hard zero


@pytest.mark.asyncio
async def test_pairwise_fallback_zero_is_not_smoothed():
    # A subtopic ranked dead last in a real pairwise comparison stays at 0 —
    # that's a genuine signal, unlike a thin LLM-count sample.
    subtopics = ["a", "b", "c"]
    comparisons = [("a", "b"), ("a", "c"), ("b", "c")]
    result = await derive_subtopic_weights(
        topic="Test", goal="job_performance", subtopics=subtopics,
        work_evidence="evidence", pairwise_comparisons=comparisons,
    )
    assert result.weights["c"] == 0
    assert sum(result.weights.values()) == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_pairwise_weights_sum_to_100_despite_stale_subtopics_arg():
    # Regression: if the caller's `subtopics` list (e.g. re-fetched from a
    # cache that regenerated with different phrasing since the ranking was
    # captured client-side) doesn't match the names in pairwise_comparisons,
    # weights must still be keyed on — and sum to 100 over — the names
    # actually in the comparisons, not silently strand votes on a mismatched
    # externally-supplied list.
    stale_subtopics = ["x", "y", "z"]  # doesn't match any name below
    comparisons = [("a", "b"), ("a", "c"), ("b", "c")]
    result = await derive_subtopic_weights(
        topic="Test", goal="job_performance", subtopics=stale_subtopics,
        pairwise_comparisons=comparisons,
    )
    assert set(result.subtopics) == {"a", "b", "c"}
    assert sum(result.weights.values()) == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_sparsity_threshold_scales_with_subtopic_count():
    # 10 mentions spread over 10 subtopics (avg 1 each) is thinner than the
    # flat MIN_EVIDENCE_THRESHOLD=5 alone would catch.
    many_subtopics = [f"s{i}" for i in range(10)]
    counts = {s: 1 for s in many_subtopics}
    with patch("app.services.subtopic_weights._count_mentions_llm", AsyncMock(return_value=counts)):
        result = await derive_subtopic_weights(
            topic="Test", goal="job_performance", subtopics=many_subtopics, work_evidence="evidence"
        )
    assert result.needs_pairwise is True
    assert result.weights is None


@pytest.mark.asyncio
async def test_sparsity_threshold_not_triggered_with_sufficient_evidence():
    subtopics = ["a", "b", "c"]
    counts = {"a": 4, "b": 3, "c": 2}  # total=9 >= max(5, 1.5*3)=5
    with patch("app.services.subtopic_weights._count_mentions_llm", AsyncMock(return_value=counts)):
        result = await derive_subtopic_weights(
            topic="Test", goal="job_performance", subtopics=subtopics, work_evidence="evidence"
        )
    assert result.needs_pairwise is False
    assert result.weights is not None


@pytest.mark.asyncio
async def test_goal_intent_never_falls_into_sparse_equal_split():
    """A one-line goal has nothing to mention-count, so routing it through the
    evidence path always tripped the sparsity threshold and collapsed to an
    equal split. The intent path scores relevance instead and must produce a
    real spread — this is the regression that made the goal cards do nothing.
    """
    subtopics = ["joins", "indexes", "transactions"]
    scores = {"joins": 9.0, "indexes": 2.0, "transactions": 0.0}
    with patch(
        "app.services.subtopic_weights._score_relevance_llm", AsyncMock(return_value=scores)
    ), patch(
        "app.services.subtopic_weights._score_proficiency_llm", AsyncMock(return_value={}),
    ):
        result = await derive_subtopic_weights(
            topic="SQL",
            goal="job_performance",
            subtopics=subtopics,
            goal_intent="My current focus is data modelling for analytics.",
        )

    assert result.needs_pairwise is False
    assert result.weights is not None
    # Not an equal split — the whole point of the intent path.
    assert result.weights["joins"] > result.weights["indexes"] > result.weights["transactions"]
    assert sum(result.weights.values()) == pytest.approx(100.0)
    # Smoothed: a 0 relevance means "not for this goal", never "never study".
    assert result.weights["transactions"] > 0


@pytest.mark.asyncio
async def test_goal_intent_skips_the_evidence_path_entirely():
    subtopics = ["a", "b"]
    counter = AsyncMock(return_value={"a": 0, "b": 0})
    with patch("app.services.subtopic_weights._count_mentions_llm", counter), patch(
        "app.services.subtopic_weights._score_relevance_llm",
        AsyncMock(return_value={"a": 5.0, "b": 1.0}),
    ), patch(
        "app.services.subtopic_weights._score_proficiency_llm", AsyncMock(return_value={}),
    ):
        result = await derive_subtopic_weights(
            topic="SQL", goal="job_performance", subtopics=subtopics, goal_intent="some goal"
        )

    counter.assert_not_awaited()
    assert result.weights["a"] > result.weights["b"]


@pytest.mark.asyncio
async def test_proficiency_only_computed_on_goal_intent_path():
    # Evidence and pairwise paths have no level-anchored intent to estimate
    # mastery from — proficiency stays None rather than a fabricated guess.
    counts = {"a": 4, "b": 3, "c": 2}
    with patch("app.services.subtopic_weights._count_mentions_llm", AsyncMock(return_value=counts)):
        result = await derive_subtopic_weights(
            topic="Test", goal="job_performance", subtopics=["a", "b", "c"], work_evidence="evidence"
        )
    assert result.proficiency is None


@pytest.mark.asyncio
async def test_proficiency_populated_and_clamped_on_goal_intent_path():
    subtopics = ["a", "b"]
    with patch(
        "app.services.subtopic_weights._score_relevance_llm",
        AsyncMock(return_value={"a": 5.0, "b": 1.0}),
    ), patch(
        "app.services.subtopic_weights._score_proficiency_llm",
        AsyncMock(return_value={"a": 70.0, "b": 15.0}),
    ):
        result = await derive_subtopic_weights(
            topic="SQL", goal="job_performance", subtopics=subtopics,
            goal_intent="some goal", current_level="intermediate", skill_gap="low",
        )

    assert result.proficiency == {"a": 70.0, "b": 15.0}


@pytest.mark.asyncio
async def test_score_proficiency_llm_defaults_missing_subtopic_to_zero_and_clamps():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_text_response('{"a": 130, "b": -5}')
    )
    with patch("app.services.subtopic_weights.anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("app.services.subtopic_weights.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-test")
            scores = await _score_proficiency_llm(
                "some intent", "SQL", ["a", "b", "c"], "beginner", "high"
            )

    assert scores == {"a": 100.0, "b": 0.0, "c": 0.0}


if __name__ == "__main__":
    import asyncio

    test_normalize_sums_to_100()
    test_normalize_zero_counts_splits_evenly()
    test_parse_json_object_strips_markdown_fence()
    test_pairwise_wins_to_counts()
    test_pairwise_wins_to_counts_ignores_stale_subtopics_list()
    test_nudge_is_clamped_to_cap()
    test_opposed_max_nudges_flag_both()
    test_small_nudge_produces_no_flag()
    asyncio.run(test_count_mentions_llm_uses_model_counts())
    asyncio.run(test_count_mentions_llm_defaults_missing_subtopic_to_zero())
    asyncio.run(test_zero_count_subtopic_gets_smoothed_nonzero_weight())
    asyncio.run(test_pairwise_fallback_zero_is_not_smoothed())
    asyncio.run(test_pairwise_weights_sum_to_100_despite_stale_subtopics_arg())
    asyncio.run(test_sparsity_threshold_scales_with_subtopic_count())
    asyncio.run(test_sparsity_threshold_not_triggered_with_sufficient_evidence())
    print("ok")
