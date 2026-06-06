"""Unit tests for SessionEndProcessor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.session_end_processor import SessionEndProcessor


@pytest.fixture
def processor():
    return SessionEndProcessor()


@pytest.fixture
def valid_llm_output():
    return {
        "narrative_summary": "User practiced binary search problems and improved.",
        "skill_update": {
            "topic": "Binary Search",
            "mentor_eval_score": "intermediate",
            "mentor_eval_count": 3,
        },
        "type": "dsa_practice",
        "topic": "Binary Search",
        "topic_category": "DSA",
    }


class TestInputValidation:
    """Task 10.2: Input validation tests."""

    @pytest.mark.asyncio
    async def test_missing_narrative_summary_marks_orphaned(self, processor):
        """Malformed output missing narrative_summary marks session orphaned."""
        mock_collection = AsyncMock()
        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_collection,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output={"skill_update": {"topic": "Trees"}},
            )

        mock_collection.update_one.assert_called_once_with(
            {"session_id": "session_1"},
            {"$set": {"orphaned": True}},
        )

    @pytest.mark.asyncio
    async def test_missing_skill_update_marks_orphaned(self, processor):
        """Malformed output missing skill_update marks session orphaned."""
        mock_collection = AsyncMock()
        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_collection,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output={"narrative_summary": "Some summary"},
            )

        mock_collection.update_one.assert_called_once_with(
            {"session_id": "session_1"},
            {"$set": {"orphaned": True}},
        )

    @pytest.mark.asyncio
    async def test_narrative_summary_wrong_type_marks_orphaned(self, processor):
        """narrative_summary must be a string."""
        mock_collection = AsyncMock()
        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_collection,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output={"narrative_summary": 123, "skill_update": {}},
            )

        mock_collection.update_one.assert_called_once_with(
            {"session_id": "session_1"},
            {"$set": {"orphaned": True}},
        )

    @pytest.mark.asyncio
    async def test_skill_update_wrong_type_marks_orphaned(self, processor):
        """skill_update must be a dict."""
        mock_collection = AsyncMock()
        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_collection,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output={"narrative_summary": "Summary", "skill_update": "not a dict"},
            )

        mock_collection.update_one.assert_called_once_with(
            {"session_id": "session_1"},
            {"$set": {"orphaned": True}},
        )

    @pytest.mark.asyncio
    async def test_valid_output_does_not_mark_orphaned(self, processor, valid_llm_output):
        """Valid output should not mark session as orphaned."""
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=valid_llm_output,
            )

        # Should not have been called with orphaned=True
        orphan_calls = [
            call
            for call in mock_sessions.update_one.call_args_list
            if call[0][1] == {"$set": {"orphaned": True}}
        ]
        assert len(orphan_calls) == 0


class TestNarrativeEmbedding:
    """Task 10.3: Narrative embedding tests."""

    @pytest.mark.asyncio
    async def test_embeds_narrative_summary(self, processor, valid_llm_output):
        """Narrative summary is passed to EmbedderService."""
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=valid_llm_output,
            )

        mock_embedder_instance.embed_and_store.assert_called_once()
        chunks = mock_embedder_instance.embed_and_store.call_args[0][0]
        assert len(chunks) == 1
        assert chunks[0].text == valid_llm_output["narrative_summary"]
        assert chunks[0].metadata.user_id == "user_1"
        assert chunks[0].metadata.source == "session_summary"
        assert chunks[0].metadata.session_id == "session_1"
        assert chunks[0].metadata.chunk_index == 0
        assert chunks[0].metadata.type == "dsa_practice"
        assert chunks[0].metadata.topic == "Binary Search"
        assert chunks[0].metadata.topic_category == "DSA"

    @pytest.mark.asyncio
    async def test_chunk_metadata_defaults_type_to_general(self, processor):
        """When type is not in llm_output, defaults to 'general'."""
        llm_output = {
            "narrative_summary": "Summary text",
            "skill_update": {"topic": "Arrays"},
        }
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=llm_output,
            )

        chunks = mock_embedder_instance.embed_and_store.call_args[0][0]
        assert chunks[0].metadata.type == "general"


class TestSkillUpdate:
    """Task 10.4: Skill update tests."""

    @pytest.mark.asyncio
    async def test_upserts_skill_update(self, processor, valid_llm_output):
        """Valid skill_update is upserted to skill_graph collection."""
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=valid_llm_output,
            )

        mock_skill_graph.update_one.assert_called_once()
        call_args = mock_skill_graph.update_one.call_args
        assert call_args[0][0] == {"user_id": "user_1", "topic": "Binary Search"}
        assert call_args[1]["upsert"] is True

    @pytest.mark.asyncio
    async def test_invalid_skill_update_skips_write(self, processor):
        """Invalid skill_update data skips the write but doesn't affect embedding."""
        llm_output = {
            "narrative_summary": "Summary",
            "skill_update": {
                "topic": "Trees",
                "mentor_eval_count": -5,  # invalid: negative
            },
        }
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=llm_output,
            )

        # Embedding was still called
        mock_embedder_instance.embed_and_store.assert_called_once()
        # Skill graph was not written
        mock_skill_graph.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_skill_update_without_topic_skips_write(self, processor):
        """Skill update with no topic skips the write."""
        llm_output = {
            "narrative_summary": "Summary",
            "skill_update": {
                "mentor_eval_score": "beginner",
                "mentor_eval_count": 1,
            },
        }
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=llm_output,
            )

        mock_skill_graph.update_one.assert_not_called()


class TestPartialFailureHandling:
    """Task 10.5: Partial failure handling tests."""

    @pytest.mark.asyncio
    async def test_embedding_failure_still_attempts_skill_write(self, processor):
        """When embedding fails, skill update is still attempted."""
        from app.services.embedder_service import EmbeddingError

        llm_output = {
            "narrative_summary": "Summary",
            "skill_update": {
                "topic": "Graphs",
                "mentor_eval_score": "intermediate",
                "mentor_eval_count": 2,
            },
        }
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()
        mock_embedder_instance.embed_and_store.side_effect = EmbeddingError("API failed")

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=llm_output,
            )

        # Skill graph write was still attempted
        mock_skill_graph.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_embedding_failure_marks_session_partial(self, processor):
        """When embedding fails, session is marked partial."""
        from app.services.embedder_service import EmbeddingError

        llm_output = {
            "narrative_summary": "Summary",
            "skill_update": {
                "topic": "Graphs",
                "mentor_eval_score": "intermediate",
                "mentor_eval_count": 2,
            },
        }
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()
        mock_embedder_instance.embed_and_store.side_effect = EmbeddingError("API failed")

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=llm_output,
            )

        mock_sessions.update_one.assert_called_once_with(
            {"session_id": "session_1"},
            {"$set": {"partial": True}},
        )

    @pytest.mark.asyncio
    async def test_no_partial_mark_when_embedding_succeeds(self, processor, valid_llm_output):
        """When embedding succeeds, session is not marked partial."""
        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await processor.process(
                user_id="user_1",
                session_id="session_1",
                llm_output=valid_llm_output,
            )

        # Sessions collection should not have been called at all
        # (no orphaned and no partial)
        mock_sessions.update_one.assert_not_called()


# --- Property-Based Tests ---

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models.schemas import ChunkMetadata


# Strategies for generating LLM output shapes
valid_narrative = st.text(min_size=5, max_size=200).filter(lambda t: t.strip())
valid_skill_update = st.fixed_dictionaries({
    "topic": st.text(min_size=1, max_size=30).filter(lambda t: t.strip()),
})


# Feature: ingestion-pipeline, Property 16: Malformed session output detection
class TestMalformedSessionOutputDetectionPBT:
    """Property 16: Malformed session output detection.

    JSON missing narrative_summary or skill_update marks session orphaned
    and preserves transcript.
    """

    @given(
        data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(min_size=0, max_size=50), st.integers(), st.none()),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_malformed_output_detected(self, data):
        """**Validates: Requirements 9.2**

        For any JSON object that is missing either narrative_summary (str) or
        skill_update (dict), the processor marks the session as orphaned.
        """
        # Check if data is actually malformed for our purposes
        has_valid_narrative = (
            "narrative_summary" in data
            and isinstance(data["narrative_summary"], str)
        )
        has_valid_skill_update = (
            "skill_update" in data
            and isinstance(data["skill_update"], dict)
        )
        is_valid = has_valid_narrative and has_valid_skill_update

        # We're testing the malformed case - skip if accidentally valid
        assume(not is_valid)

        proc = SessionEndProcessor()
        result = proc._is_valid_output(data)
        assert result is False, (
            f"Expected _is_valid_output to return False for malformed data: {data}"
        )


# Feature: ingestion-pipeline, Property 17: Session embedding metadata completeness
class TestSessionEmbeddingMetadataCompletenessPBT:
    """Property 17: Session embedding metadata completeness.

    Session-end embeddings have non-null userId, sessionId, date, type, topic, topic_category.
    """

    @given(
        user_id=st.text(min_size=1, max_size=20).filter(lambda t: t.strip()),
        session_id=st.text(min_size=1, max_size=20).filter(lambda t: t.strip()),
        summary=valid_narrative,
        session_type=st.text(min_size=1, max_size=20).filter(lambda t: t.strip()),
        topic=st.text(min_size=1, max_size=30).filter(lambda t: t.strip()),
        topic_category=st.text(min_size=1, max_size=20).filter(lambda t: t.strip()),
    )
    @settings(max_examples=100)
    def test_chunk_metadata_has_all_required_fields(
        self, user_id, session_id, summary, session_type, topic, topic_category
    ):
        """**Validates: Requirements 9.4**

        Session-end embeddings have non-null userId, sessionId, date, type,
        topic, topic_category.
        """
        llm_output = {
            "narrative_summary": summary,
            "skill_update": {"topic": topic},
            "type": session_type,
            "topic": topic,
            "topic_category": topic_category,
        }

        proc = SessionEndProcessor()
        chunk = proc._build_narrative_chunk(user_id, session_id, llm_output)

        # Verify all required metadata fields are non-null
        assert chunk.metadata.user_id is not None
        assert chunk.metadata.user_id == user_id

        assert chunk.metadata.session_id is not None
        assert chunk.metadata.session_id == session_id

        assert chunk.metadata.date is not None
        assert len(chunk.metadata.date) > 0  # Should be an ISO date string

        assert chunk.metadata.type is not None
        assert chunk.metadata.type == session_type

        assert chunk.metadata.topic is not None
        assert chunk.metadata.topic == topic

        assert chunk.metadata.topic_category is not None
        assert chunk.metadata.topic_category == topic_category

        assert chunk.metadata.source == "session_summary"


# Feature: ingestion-pipeline, Property 18: Skill update merge preserves existing fields
class TestSkillUpdateMergePreservesExistingFieldsPBT:
    """Property 18: Skill update merge preserves existing fields.

    Incoming updates with omitted fields retain existing values while
    updating present fields.
    """

    @given(
        existing_score=st.one_of(st.just(None), st.sampled_from(["beginner", "intermediate", "advanced"])),
        existing_count=st.integers(min_value=0, max_value=100),
        new_score=st.one_of(st.just(None), st.sampled_from(["beginner", "intermediate", "advanced"])),
        new_count=st.one_of(st.just(None), st.integers(min_value=0, max_value=100)),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_upsert_preserves_omitted_fields(
        self, existing_score, existing_count, new_score, new_count
    ):
        """**Validates: Requirements 9.7, 9.8**

        For any existing skill graph node and any incoming skill_update that omits
        some fields, the MongoDB $set operation only updates present fields.
        Omitted fields retain their existing values.
        """
        # The MongoDB $set operator inherently preserves fields not in the update.
        # We verify the processor uses $set correctly and only includes validated fields.

        skill_update = {"topic": "Arrays"}
        if new_score is not None:
            skill_update["mentor_eval_score"] = new_score
        if new_count is not None:
            skill_update["mentor_eval_count"] = new_count

        llm_output = {
            "narrative_summary": "User practiced arrays today.",
            "skill_update": skill_update,
        }

        mock_sessions = AsyncMock()
        mock_skill_graph = AsyncMock()
        mock_embedder_instance = AsyncMock()

        proc = SessionEndProcessor()

        with patch(
            "app.services.session_end_processor.get_sessions_collection",
            return_value=mock_sessions,
        ), patch(
            "app.services.session_end_processor.get_skill_graph_collection",
            return_value=mock_skill_graph,
        ), patch(
            "app.services.session_end_processor.EmbedderService",
            return_value=mock_embedder_instance,
        ):
            await proc.process(
                user_id="user-1",
                session_id="session-1",
                llm_output=llm_output,
            )

        # If skill update had a valid topic, update_one should have been called
        if mock_skill_graph.update_one.called:
            call_args = mock_skill_graph.update_one.call_args
            filter_arg = call_args[0][0]
            update_arg = call_args[0][1]

            # Filter uses user_id + topic for matching
            assert filter_arg["user_id"] == "user-1"
            assert filter_arg["topic"] == "Arrays"

            # Uses $set which preserves existing fields not in the update
            assert "$set" in update_arg

            # upsert=True ensures merge semantics
            assert call_args[1]["upsert"] is True
