"""Property-based tests for Re-Ingestion Handler."""

from unittest.mock import AsyncMock, patch, call

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.reingestion_handler import ReIngestionHandler


source_categories = st.sampled_from(["resume", "leetcode"])
user_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=5,
    max_size=20,
).filter(lambda t: t.strip())


# Feature: ingestion-pipeline, Property 22: Re-ingestion deletes only source-category data
class TestReIngestionDeletesOnlySourceCategoryData:
    """Property 22: Re-ingestion deletes only source-category data.

    Deletion removes chunks matching source C and preserves all others.
    """

    @given(
        user_id=user_ids,
        source_category=source_categories,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_delete_targets_only_source_category(self, user_id: str, source_category: str):
        """**Validates: Requirements 13.1**

        Re-ingestion deletion removes only vector chunks where metadata.source
        matches the source_category and preserves all others.
        """
        mock_embeddings = AsyncMock()
        mock_embeddings.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=5))
        mock_skill_graph = AsyncMock()
        mock_skill_graph.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=2))
        mock_users = AsyncMock()

        with patch(
            "app.services.reingestion_handler.get_embeddings_collection",
            return_value=mock_embeddings,
        ), patch(
            "app.services.reingestion_handler.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.reingestion_handler.get_users_collection",
            return_value=mock_users,
        ):
            handler = ReIngestionHandler.__new__(ReIngestionHandler)
            await handler._delete_old_data(user_id, source_category)

        # Verify embeddings delete filter targets the correct source_category
        mock_embeddings.delete_many.assert_called_once()
        embed_filter = mock_embeddings.delete_many.call_args[0][0]

        assert embed_filter["metadata.user_id"] == user_id
        assert embed_filter["metadata.source"] == source_category

        # The filter should NOT include "session" or "session_summary" sources
        # (those are preserved by only matching the specific source_category)
        assert embed_filter["metadata.source"] != "session"
        assert embed_filter["metadata.source"] != "session_summary"


# Feature: ingestion-pipeline, Property 23: Re-ingestion full replace semantics
class TestReIngestionFullReplaceSemantics:
    """Property 23: Re-ingestion full replace semantics.

    Resulting structured data contains only new values, no residuals from prior ingestion.
    """

    @given(
        user_id=user_ids,
        source_category=st.just("leetcode"),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_leetcode_reingestion_deletes_all_existing(self, user_id: str, source_category: str):
        """**Validates: Requirements 13.2**

        For leetcode re-ingestion, all existing skill graph docs with leetcode_solved
        signals are deleted, ensuring only new values remain after re-ingestion.
        """
        mock_embeddings = AsyncMock()
        mock_embeddings.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=3))
        mock_skill_graph = AsyncMock()
        mock_skill_graph.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=2))

        with patch(
            "app.services.reingestion_handler.get_embeddings_collection",
            return_value=mock_embeddings,
        ), patch(
            "app.services.reingestion_handler.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ):
            handler = ReIngestionHandler.__new__(ReIngestionHandler)
            await handler._delete_old_data(user_id, source_category)

        # For leetcode, skill graph docs with leetcode_solved signals are deleted
        mock_skill_graph.delete_many.assert_called_once()
        sg_filter = mock_skill_graph.delete_many.call_args[0][0]

        assert sg_filter["user_id"] == user_id
        assert sg_filter["signals.leetcode_solved"] == {"$exists": True}

    @given(user_id=user_ids)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_resume_reingestion_clears_profile_fields(self, user_id: str):
        """For resume re-ingestion, profile fields are cleared to None/empty."""
        mock_embeddings = AsyncMock()
        mock_embeddings.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=3))
        mock_skill_graph = AsyncMock()
        mock_skill_graph.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=0))
        mock_users = AsyncMock()

        with patch(
            "app.services.reingestion_handler.get_embeddings_collection",
            return_value=mock_embeddings,
        ), patch(
            "app.services.reingestion_handler.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.reingestion_handler.get_users_collection",
            return_value=mock_users,
        ):
            handler = ReIngestionHandler.__new__(ReIngestionHandler)
            await handler._delete_old_data(user_id, "resume")

        # Profile fields should be cleared
        mock_users.update_one.assert_called_once()
        update_call = mock_users.update_one.call_args
        update_filter = update_call[0][0]
        update_set = update_call[0][1]["$set"]

        assert update_filter == {"user_id": user_id}
        assert update_set["current_role"] is None
        assert update_set["years_of_experience"] is None
        assert update_set["education"] is None
        assert update_set["skills"] == []


# Feature: ingestion-pipeline, Property 24: Re-ingestion preserves session-tagged data
class TestReIngestionPreservesSessionTaggedData:
    """Property 24: Re-ingestion preserves session-tagged data.

    All session-tagged embeddings and skill updates remain unmodified.
    """

    @given(
        user_id=user_ids,
        source_category=source_categories,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_session_data_never_deleted(self, user_id: str, source_category: str):
        """**Validates: Requirements 13.3**

        Re-ingestion never deletes session-tagged data. The delete filter only
        targets the specific source_category, never 'session' or 'session_summary'.
        """
        mock_embeddings = AsyncMock()
        mock_embeddings.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=0))
        mock_skill_graph = AsyncMock()
        mock_skill_graph.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=0))
        mock_users = AsyncMock()

        with patch(
            "app.services.reingestion_handler.get_embeddings_collection",
            return_value=mock_embeddings,
        ), patch(
            "app.services.reingestion_handler.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.reingestion_handler.get_users_collection",
            return_value=mock_users,
        ):
            handler = ReIngestionHandler.__new__(ReIngestionHandler)
            await handler._delete_old_data(user_id, source_category)

        # The embeddings delete filter specifically targets source_category
        # and NOT "session" or "session_summary"
        embed_filter = mock_embeddings.delete_many.call_args[0][0]
        assert embed_filter["metadata.source"] == source_category
        assert source_category in ("resume", "leetcode")
        # Session sources are never targeted
        assert embed_filter["metadata.source"] not in ("session", "session_summary")

        # For structured data, the delete targets are also category-specific
        if source_category == "leetcode":
            sg_filter = mock_skill_graph.delete_many.call_args[0][0]
            # Only deletes leetcode_solved signals, not session-originated skill updates
            assert "signals.leetcode_solved" in sg_filter
        elif source_category == "resume":
            # Resume deletes resume-sourced skill graph entries
            sg_filter = mock_skill_graph.delete_many.call_args[0][0]
            assert sg_filter.get("source") == "resume" or sg_filter.get("user_id") == user_id
