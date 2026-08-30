"""Unit tests for app/services/vector_search.py — shared Atlas Vector Search plumbing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.vector_search import (
    VECTOR_INDEX_NAME,
    delete_topic_document,
    delete_vectors,
    embed_and_upsert,
    ensure_vector_index,
    list_topic_documents,
    vector_search,
)


class TestEnsureVectorIndex:
    @pytest.mark.asyncio
    async def test_creates_index_when_missing(self):
        col = MagicMock()
        col.list_search_indexes.return_value.to_list = AsyncMock(return_value=[])
        col.create_search_index = AsyncMock()

        with patch("app.services.vector_search.embeddings_col", return_value=col):
            await ensure_vector_index()

        col.create_search_index.assert_called_once()
        assert col.create_search_index.call_args[0][0]["name"] == VECTOR_INDEX_NAME

    @pytest.mark.asyncio
    async def test_skips_creation_when_already_exists(self):
        col = MagicMock()
        col.list_search_indexes.return_value.to_list = AsyncMock(
            return_value=[{"name": VECTOR_INDEX_NAME}]
        )
        col.create_search_index = AsyncMock()

        with patch("app.services.vector_search.embeddings_col", return_value=col):
            await ensure_vector_index()

        col.create_search_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_errors_fail_open(self):
        col = MagicMock()
        col.list_search_indexes.side_effect = Exception("Atlas tier doesn't support this")

        with patch("app.services.vector_search.embeddings_col", return_value=col):
            await ensure_vector_index()  # must not raise


class TestEmbedAndUpsert:
    @pytest.mark.asyncio
    async def test_writes_nothing_when_embedding_fails(self):
        col = MagicMock()
        col.update_one = AsyncMock()

        with (
            patch("app.services.vector_search.embeddings_col", return_value=col),
            patch("app.services.vector_search.embed_text", AsyncMock(return_value=[])),
        ):
            ok = await embed_and_upsert("v1", "some text", "u1", "ingestion")

        assert ok is False
        col.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_upserts_with_embedding_field_on_success(self):
        col = MagicMock()
        col.update_one = AsyncMock()

        with (
            patch("app.services.vector_search.embeddings_col", return_value=col),
            patch("app.services.vector_search.embed_text", AsyncMock(return_value=[0.1, 0.2])),
        ):
            ok = await embed_and_upsert(
                "v1", "some text", "u1", "summary_block", metadata={"topic_id": "t1"}
            )

        assert ok is True
        filter_arg, update_arg = col.update_one.call_args[0]
        assert filter_arg == {"vector_id": "v1"}
        doc = update_arg["$set"]
        assert doc["embedding"] == [0.1, 0.2]
        assert doc["user_id"] == "u1"
        assert doc["metadata"] == {"source": "summary_block", "topic_id": "t1"}


class TestDeleteVectors:
    @pytest.mark.asyncio
    async def test_noop_on_empty_list(self):
        col = MagicMock()
        col.delete_many = AsyncMock()
        with patch("app.services.vector_search.embeddings_col", return_value=col):
            await delete_vectors([])
        col.delete_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_by_vector_id(self):
        col = MagicMock()
        col.delete_many = AsyncMock()
        with patch("app.services.vector_search.embeddings_col", return_value=col):
            await delete_vectors(["v1", "v2"])
        col.delete_many.assert_called_once_with({"vector_id": {"$in": ["v1", "v2"]}})


class TestListTopicDocuments:
    @pytest.mark.asyncio
    async def test_returns_aggregated_rows(self):
        col = MagicMock()
        rows = [{"filename": "notes.pdf", "chunkCount": 3, "uploadedAt": "2026-08-30T00:00:00"}]
        col.aggregate.return_value.to_list = AsyncMock(return_value=rows)
        with patch("app.services.vector_search.embeddings_col", return_value=col):
            result = await list_topic_documents("topic-abc", "u1")

        assert result == rows
        pipeline = col.aggregate.call_args[0][0]
        assert pipeline[0]["$match"] == {
            "user_id": "u1", "metadata.topic_id": "topic-abc", "metadata.source": "topic_document",
        }


class TestDeleteTopicDocument:
    @pytest.mark.asyncio
    async def test_deletes_by_topic_and_filename(self):
        col = MagicMock()
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
        with patch("app.services.vector_search.embeddings_col", return_value=col):
            deleted = await delete_topic_document("topic-abc", "u1", "notes.pdf")

        assert deleted == 3
        col.delete_many.assert_called_once_with({
            "user_id": "u1", "metadata.topic_id": "topic-abc",
            "metadata.source": "topic_document", "metadata.filename": "notes.pdf",
        })

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_matched(self):
        col = MagicMock()
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        with patch("app.services.vector_search.embeddings_col", return_value=col):
            deleted = await delete_topic_document("topic-abc", "u1", "missing.pdf")

        assert deleted == 0


class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_returns_empty_when_query_embedding_fails(self):
        with patch("app.services.vector_search.embed_text", AsyncMock(return_value=[])):
            result = await vector_search("query", "u1", "ingestion")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_aggregate_failure(self):
        col = MagicMock()
        col.aggregate.side_effect = Exception("index not ready")

        with (
            patch("app.services.vector_search.embeddings_col", return_value=col),
            patch("app.services.vector_search.embed_text", AsyncMock(return_value=[0.1])),
        ):
            result = await vector_search("query", "u1", "ingestion")

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_user_and_source_and_optional_topic(self):
        col = MagicMock()
        col.aggregate.return_value.to_list = AsyncMock(return_value=[{"text": "hit"}])

        with (
            patch("app.services.vector_search.embeddings_col", return_value=col),
            patch("app.services.vector_search.embed_text", AsyncMock(return_value=[0.1])),
        ):
            result = await vector_search("query", "u1", "summary_block", topic_id="t1")

        assert result == [{"text": "hit"}]
        pipeline = col.aggregate.call_args[0][0]
        vs_stage = pipeline[0]["$vectorSearch"]
        assert vs_stage["filter"] == {
            "user_id": "u1",
            "metadata.source": "summary_block",
            "metadata.topic_id": "t1",
        }
