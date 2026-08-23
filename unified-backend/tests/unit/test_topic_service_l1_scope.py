"""Unit tests for TopicService.get_topic's lazy l1_scope compute/cache.

Tests cover:
- Cache hit (matching profileStamp) skips classify_relevance
- Cache miss (missing fields, or stale stamp) recomputes and persists
- classify_relevance failure leaves the topic doc unchanged (no partial write)
- No profile found short-circuits without calling classify_relevance
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.services.l1_scope import compute_profile_stamp
from app.services.topic_service import TopicService


@pytest.fixture
def topic_service():
    return TopicService()


@pytest.fixture
def base_topic():
    return {
        "topicId": "topic-123",
        "userId": "user-abc",
        "title": "React",
        "status": "active",
    }


@pytest.fixture
def profile_with_situations():
    return {
        "user_id": "user-abc",
        "learning_context_detail": {
            "situations": ["preparing for interview backend engineer"],
            "contexts": ["senior backend, Mumbai"],
        },
    }


def _judgment(text: str, verdict: str = "relevant") -> dict:
    return {"situation": text, "verdict": verdict, "reason": "because"}


class TestGetTopicL1ScopeCacheHit:
    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_matching_stamp_skips_classify_relevance(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic, profile_with_situations,
    ):
        stamp = compute_profile_stamp(["preparing for interview backend engineer"], ["senior backend, Mumbai"], [])
        topic = {**base_topic, "l1_scope": [_judgment("x", "relevant")], "profileStamp": stamp}

        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = topic
        mock_topics_col.return_value = mock_topics

        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = profile_with_situations
        mock_profiles_col.return_value = mock_profiles

        result = await topic_service.get_topic("topic-123", "user-abc")

        mock_classify.assert_not_called()
        mock_topics.update_one.assert_not_called()
        assert result["l1_scope"] == topic["l1_scope"]

    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_focus_area_change_invalidates_cache(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic, profile_with_situations,
    ):
        """A stamp computed before focus_areas existed must not match a
        profile that now has them — otherwise a focus_areas edit would
        silently never trigger a recompute."""
        stale_stamp = compute_profile_stamp(
            ["preparing for interview backend engineer"], ["senior backend, Mumbai"], [],
        )
        topic = {**base_topic, "l1_scope": [_judgment("x", "relevant")], "profileStamp": stale_stamp}

        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = topic
        mock_topics_col.return_value = mock_topics

        profile = {**profile_with_situations, "focus_areas": ["Enterprise REST API development"]}
        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = profile
        mock_profiles_col.return_value = mock_profiles

        mock_classify.return_value = [_judgment("new", "relevant")]

        await topic_service.get_topic("topic-123", "user-abc")

        mock_classify.assert_called_once()
        assert mock_classify.call_args[0][3] == ["Enterprise REST API development"]


class TestGetTopicL1ScopeCacheMiss:
    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_missing_fields_triggers_recompute(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic, profile_with_situations,
    ):
        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = dict(base_topic)  # no l1_scope/profileStamp
        mock_topics_col.return_value = mock_topics

        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = profile_with_situations
        mock_profiles_col.return_value = mock_profiles

        judgments = [
            _judgment("preparing for interview backend engineer", "irrelevant"),
            _judgment("senior backend, Mumbai", "relevant"),
        ]
        mock_classify.return_value = judgments
        # classify_relevance itself doesn't emit userResolved — _ensure_l1_scope's
        # merge step adds it (False, since there's no prior resolved entry here).
        expected = [{**j, "userResolved": False} for j in judgments]

        result = await topic_service.get_topic("topic-123", "user-abc")

        mock_classify.assert_called_once()
        assert mock_classify.call_args[0][0] == "React"
        mock_topics.update_one.assert_called_once()
        set_fields = mock_topics.update_one.call_args[0][1]["$set"]
        assert set_fields["l1_scope"] == expected
        assert "profileStamp" in set_fields
        assert result["l1_scope"] == expected

    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_stale_stamp_triggers_recompute(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic, profile_with_situations,
    ):
        stale_topic = {**base_topic, "l1_scope": [_judgment("old", "relevant")], "profileStamp": "stale-hash"}

        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = stale_topic
        mock_topics_col.return_value = mock_topics

        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = profile_with_situations
        mock_profiles_col.return_value = mock_profiles

        mock_classify.return_value = [_judgment("new", "relevant")]

        result = await topic_service.get_topic("topic-123", "user-abc")

        mock_classify.assert_called_once()
        mock_topics.update_one.assert_called_once()
        assert result["l1_scope"] == [{**_judgment("new", "relevant"), "userResolved": False}]

    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_user_resolved_entry_survives_recompute(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic, profile_with_situations,
    ):
        """A manual answer for one item must not get silently re-classified
        (and possibly reversed) just because an unrelated profile edit
        invalidated the whole topic's profileStamp."""
        resolved_entry = {
            "situation": "preparing for interview backend engineer",
            "verdict": "relevant",  # user overrode an earlier "uncertain"/"irrelevant"
            "reason": "user confirmed",
            "userResolved": True,
        }
        stale_topic = {**base_topic, "l1_scope": [resolved_entry], "profileStamp": "stale-hash"}

        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = stale_topic
        mock_topics_col.return_value = mock_topics

        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = profile_with_situations
        mock_profiles_col.return_value = mock_profiles

        # Fresh classification disagrees with the user's earlier answer —
        # it must lose to the carried-forward resolved entry.
        mock_classify.return_value = [
            _judgment("preparing for interview backend engineer", "irrelevant"),
            _judgment("senior backend, Mumbai", "relevant"),
        ]

        result = await topic_service.get_topic("topic-123", "user-abc")

        resolved_result = next(
            e for e in result["l1_scope"] if e["situation"] == "preparing for interview backend engineer"
        )
        assert resolved_result == resolved_entry
        other_result = next(e for e in result["l1_scope"] if e["situation"] == "senior backend, Mumbai")
        assert other_result["userResolved"] is False


class TestGetTopicL1ScopeFailureHandling:
    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_classify_relevance_failure_leaves_topic_unchanged(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic, profile_with_situations,
    ):
        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = dict(base_topic)
        mock_topics_col.return_value = mock_topics

        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = profile_with_situations
        mock_profiles_col.return_value = mock_profiles

        mock_classify.side_effect = ValueError("count mismatch")

        result = await topic_service.get_topic("topic-123", "user-abc")

        mock_topics.update_one.assert_not_called()
        assert "l1_scope" not in result
        assert "profileStamp" not in result

    @pytest.mark.asyncio
    @patch("app.services.topic_service.classify_relevance")
    @patch("app.services.topic_service.profiles_col")
    @patch("app.services.topic_service.topics_col")
    async def test_no_profile_short_circuits(
        self, mock_topics_col, mock_profiles_col, mock_classify,
        topic_service, base_topic,
    ):
        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = dict(base_topic)
        mock_topics_col.return_value = mock_topics

        mock_profiles = AsyncMock()
        mock_profiles.find_one.return_value = None
        mock_profiles_col.return_value = mock_profiles

        result = await topic_service.get_topic("topic-123", "user-abc")

        mock_classify.assert_not_called()
        mock_topics.update_one.assert_not_called()
        assert "l1_scope" not in result


class TestResolveL1ScopeItem:
    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_resolve_updates_matching_entry(self, mock_topics_col, topic_service, base_topic):
        topic = {**base_topic, "l1_scope": [
            {"situation": "preparing for interviews", "verdict": "uncertain", "reason": "hard to tell",
             "userResolved": False},
            {"situation": "other thing", "verdict": "relevant", "reason": "x", "userResolved": False},
        ]}
        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = topic
        mock_topics_col.return_value = mock_topics

        await topic_service.resolve_l1_scope_item("topic-123", "user-abc", "preparing for interviews", True)

        mock_topics.update_one.assert_called_once()
        set_fields = mock_topics.update_one.call_args[0][1]["$set"]
        resolved = next(e for e in set_fields["l1_scope"] if e["situation"] == "preparing for interviews")
        assert resolved["verdict"] == "relevant"
        assert resolved["userResolved"] is True
        untouched = next(e for e in set_fields["l1_scope"] if e["situation"] == "other thing")
        assert untouched["userResolved"] is False

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_resolve_relevant_false_sets_irrelevant(self, mock_topics_col, topic_service, base_topic):
        topic = {**base_topic, "l1_scope": [
            {"situation": "x", "verdict": "uncertain", "reason": "y", "userResolved": False},
        ]}
        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = topic
        mock_topics_col.return_value = mock_topics

        await topic_service.resolve_l1_scope_item("topic-123", "user-abc", "x", False)

        set_fields = mock_topics.update_one.call_args[0][1]["$set"]
        assert set_fields["l1_scope"][0]["verdict"] == "irrelevant"
        assert set_fields["l1_scope"][0]["userResolved"] is True

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_resolve_topic_not_found_raises_404(self, mock_topics_col, topic_service):
        from fastapi import HTTPException

        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = None
        mock_topics_col.return_value = mock_topics

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.resolve_l1_scope_item("topic-123", "user-abc", "x", True)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("app.services.topic_service.topics_col")
    async def test_resolve_no_matching_entry_raises_404(self, mock_topics_col, topic_service, base_topic):
        from fastapi import HTTPException

        topic = {**base_topic, "l1_scope": [
            {"situation": "something else", "verdict": "relevant", "reason": "x", "userResolved": False},
        ]}
        mock_topics = AsyncMock()
        mock_topics.find_one.return_value = topic
        mock_topics_col.return_value = mock_topics

        with pytest.raises(HTTPException) as exc_info:
            await topic_service.resolve_l1_scope_item("topic-123", "user-abc", "not present", True)
        assert exc_info.value.status_code == 404
        mock_topics.update_one.assert_not_called()
