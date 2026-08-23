"""Unit tests for GET /api/profile/situations/quality's stamp-based cache.

Covers:
- Matching stamp returns the cached judgments without calling the LLM
- Stale/missing stamp (facts added/edited) triggers a recompute and persists
  the fresh judgments + stamp
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.fact_quality import compute_situations_stamp


@pytest.mark.asyncio
async def test_matching_stamp_skips_llm_call():
    from app.routers.profile import get_situations_quality

    situations = ["I am a backend engineer"]
    stamp = compute_situations_stamp(situations)
    cached_judgments = [{"text": situations[0], "is_fact": True, "reason": "states a role", "rewrite": None}]

    doc = {
        "learning_context_detail": {"situations": situations},
        "situation_quality": cached_judgments,
        "situationQualityStamp": stamp,
    }

    with patch("app.routers.profile.profiles_col") as mock_col, \
         patch("app.routers.profile.classify_fact_quality", new_callable=AsyncMock) as mock_classify:
        mock_col.return_value.find_one = AsyncMock(return_value=doc)

        result = await get_situations_quality(user_id="user-1")

        mock_classify.assert_not_called()
        assert result == {"judgments": cached_judgments}


@pytest.mark.asyncio
async def test_stale_stamp_recomputes_and_persists():
    from app.routers.profile import get_situations_quality

    situations = ["I am a backend engineer", "Cloud architecture"]
    doc = {
        "learning_context_detail": {"situations": situations},
        "situation_quality": [{"text": "old", "is_fact": True, "reason": "stale", "rewrite": None}],
        "situationQualityStamp": "stale-hash",
    }
    fresh_judgments = [
        {"text": situations[0], "is_fact": True, "reason": "states a role", "rewrite": None},
        {"text": situations[1], "is_fact": False, "reason": "names a topic", "rewrite": "I have experience with cloud architecture"},
    ]

    with patch("app.routers.profile.profiles_col") as mock_col, \
         patch("app.routers.profile.classify_fact_quality", new_callable=AsyncMock) as mock_classify:
        mock_col.return_value.find_one = AsyncMock(return_value=doc)
        mock_col.return_value.update_one = AsyncMock()
        mock_classify.return_value = fresh_judgments

        result = await get_situations_quality(user_id="user-1")

        mock_classify.assert_called_once_with(situations)
        assert result == {"judgments": fresh_judgments}

        update_call = mock_col.return_value.update_one.call_args
        set_fields = update_call.args[1]["$set"]
        assert set_fields["situation_quality"] == fresh_judgments
        assert set_fields["situationQualityStamp"] == compute_situations_stamp(situations)


@pytest.mark.asyncio
async def test_no_prior_quality_recomputes():
    from app.routers.profile import get_situations_quality

    situations = ["I am a backend engineer"]
    doc = {"learning_context_detail": {"situations": situations}}

    with patch("app.routers.profile.profiles_col") as mock_col, \
         patch("app.routers.profile.classify_fact_quality", new_callable=AsyncMock) as mock_classify:
        mock_col.return_value.find_one = AsyncMock(return_value=doc)
        mock_col.return_value.update_one = AsyncMock()
        mock_classify.return_value = [{"text": situations[0], "is_fact": True, "reason": "x", "rewrite": None}]

        await get_situations_quality(user_id="user-1")

        mock_classify.assert_called_once()
