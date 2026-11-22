"""Unit tests for YouTube video ingest: URL parsing, timed chunking, the
background job, and the videos router."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings
from app.services.extraction import chunk_text
from app.services.video_ingest import build_timed_chunks, format_timestamp, run_video_ingest
from app.services.youtube_transcript import (
    Segment,
    Transcript,
    TranscriptUnavailable,
    parse_video_id,
)


@pytest.fixture(autouse=True)
def _settings():
    get_settings.cache_clear()
    env = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "MENTORMAN_API_KEY": "test-api-key",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "VOYAGE_API_KEY": "voy-test",
    }
    with patch.dict(os.environ, env, clear=True):
        get_settings()
        yield
    get_settings.cache_clear()


class TestParseVideoId:
    @pytest.mark.parametrize("value", [
        "https://www.youtube.com/watch?v=aircAruvnKk",
        "https://youtube.com/watch?feature=share&v=aircAruvnKk&t=30",
        "https://youtu.be/aircAruvnKk?si=abc",
        "https://www.youtube.com/shorts/aircAruvnKk",
        "https://www.youtube.com/embed/aircAruvnKk",
        "https://m.youtube.com/live/aircAruvnKk",
        "aircAruvnKk",
    ])
    def test_accepts_common_forms(self, value):
        assert parse_video_id(value) == "aircAruvnKk"

    @pytest.mark.parametrize("value", ["", "https://example.com/watch?v=x", "not a url", "abc"])
    def test_rejects_others(self, value):
        assert parse_video_id(value) is None


def _segments(n: int, words_per: int = 12, seconds: float = 4.0) -> list[Segment]:
    return [
        Segment(text=" ".join(f"w{i}_{j}" for j in range(words_per)), start=i * seconds, duration=seconds)
        for i in range(n)
    ]


class TestBuildTimedChunks:
    def test_full_transcript_is_chunked_with_live_chunker(self):
        segs = _segments(400)
        chunks = build_timed_chunks(segs)
        full_text = " ".join(s.text for s in segs)
        # Same chunk boundaries as uploaded documents (1000/200).
        assert [c["text"] for c in chunks] == chunk_text(full_text)
        # Nothing dropped: first and last words are present.
        assert chunks[0]["text"].startswith("w0_0")
        assert chunks[-1]["text"].endswith("w399_11")

    def test_chunks_overlap(self):
        chunks = build_timed_chunks(_segments(200))
        for a, b in zip(chunks, chunks[1:]):
            tail = a["text"][-100:].split(" ")[-2]
            assert tail in b["text"]

    def test_timestamps_cover_chunk_and_increase(self):
        segs = _segments(300)
        chunks = build_timed_chunks(segs)
        assert chunks[0]["start_seconds"] == 0
        assert chunks[-1]["end_seconds"] == segs[-1].start + segs[-1].duration
        for c in chunks:
            assert c["start_seconds"] < c["end_seconds"]
        starts = [c["start_seconds"] for c in chunks]
        assert starts == sorted(starts)

    def test_timestamp_matches_text(self):
        # The live chunker may start a chunk mid-word, so read the segment
        # from the first whole word: the chunk starts in that segment or the
        # one just before it.
        segs = _segments(300)
        for c in build_timed_chunks(segs):
            second_word = c["text"].split(" ")[1]
            seg_start = segs[int(second_word[1:].split("_")[0])].start
            assert seg_start - 4.0 <= c["start_seconds"] <= seg_start

    def test_empty(self):
        assert build_timed_chunks([]) == []


def test_format_timestamp():
    assert format_timestamp(75.9) == "1:15"
    assert format_timestamp(3725) == "1:02:05"


class TestRunVideoIngest:
    @pytest.fixture
    def cols(self):
        videos, embeddings = MagicMock(), MagicMock()
        videos.update_one = AsyncMock()
        embeddings.delete_many = AsyncMock()
        embeddings.insert_many = AsyncMock()
        with (
            patch("app.services.video_ingest.videos_col", return_value=videos),
            patch("app.services.video_ingest.embeddings_col", return_value=embeddings),
        ):
            yield videos, embeddings

    @staticmethod
    def _last_set(videos) -> dict:
        return videos.update_one.await_args_list[-1].args[1]["$set"]

    @pytest.mark.asyncio
    async def test_stores_every_chunk_with_metadata_and_summary(self, cols):
        videos, embeddings = cols
        segs = _segments(300)
        transcript = Transcript(segments=segs, language="en", source="captions")
        n_chunks = len(build_timed_chunks(segs))

        async def fake_embed(texts):
            return [[0.1] * 4 for _ in texts]

        with (
            patch("app.services.video_ingest.fetch_title", return_value="Neural nets"),
            patch("app.services.video_ingest.fetch_transcript", return_value=transcript),
            patch("app.services.video_ingest.embed_texts", side_effect=fake_embed),
            patch("app.services.video_ingest._summarize", AsyncMock(return_value="It explains neurons.")),
            patch("app.services.video_ingest.embed_and_upsert", AsyncMock(return_value=True)) as l3,
        ):
            await run_video_ingest("u1", "t1", "aircAruvnKk")

        rows = embeddings.insert_many.await_args.args[0]
        assert len(rows) == n_chunks
        meta = rows[3]["metadata"]
        assert rows[3]["user_id"] == "u1"
        assert meta["source"] == "video_transcript"
        assert meta["video_id"] == "aircAruvnKk"
        assert meta["topic_id"] == "t1"
        assert meta["chunk_index"] == 3
        assert meta["start_seconds"] < meta["end_seconds"]
        assert len({r["vector_id"] for r in rows}) == n_chunks
        # Old chunks for this video are replaced, not duplicated.
        embeddings.delete_many.assert_awaited_once()

        # Only the short summary goes to L3, never the transcript.
        l3_kwargs = l3.await_args.kwargs
        assert l3_kwargs["source"] == "summary_block"
        assert "It explains neurons." in l3_kwargs["text"]
        assert len(l3_kwargs["text"]) < 300

        final = self._last_set(videos)
        assert final["status"] == "completed"
        assert final["summary"] == "It explains neurons."

    @pytest.mark.asyncio
    async def test_no_transcript_marks_failed_with_reason(self, cols):
        videos, embeddings = cols
        with (
            patch("app.services.video_ingest.fetch_title", return_value=None),
            patch(
                "app.services.video_ingest.fetch_transcript",
                side_effect=TranscriptUnavailable("This video has no captions"),
            ),
        ):
            await run_video_ingest("u1", "t1", "aircAruvnKk")
        final = self._last_set(videos)
        assert final["status"] == "failed"
        assert final["error"] == "This video has no captions"
        embeddings.insert_many.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embedding_error_marks_failed_and_stores_nothing(self, cols):
        videos, embeddings = cols
        transcript = Transcript(segments=_segments(50), language="en", source="captions")
        with (
            patch("app.services.video_ingest.fetch_title", return_value="T"),
            patch("app.services.video_ingest.fetch_transcript", return_value=transcript),
            patch("app.services.video_ingest.embed_texts", AsyncMock(side_effect=Exception("invalid api key"))),
        ):
            await run_video_ingest("u1", "t1", "aircAruvnKk")
        final = self._last_set(videos)
        assert final["status"] == "failed"
        assert "invalid api key" in final["error"]
        embeddings.insert_many.assert_not_awaited()


class TestVideosRouter:
    @pytest.fixture
    def headers(self):
        return {"X-User-Id": "user-123", "X-Api-Key": "test-api-key"}

    @pytest.mark.asyncio
    async def test_add_video_queues_job(self, headers):
        video = {"video_id": "aircAruvnKk", "status": "queued"}
        with (
            patch("app.routers.videos._topic_service.get_topic", AsyncMock(return_value={})),
            patch("app.routers.videos.get_video", AsyncMock(return_value=None)),
            patch("app.routers.videos.create_video_job", AsyncMock(return_value=video)),
            patch("app.routers.videos.run_video_ingest", AsyncMock()) as job,
        ):
            from app.main import app

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/topic/t1/video", json={"url": "https://youtu.be/aircAruvnKk"}, headers=headers
                )
        assert resp.status_code == 202
        assert resp.json()["video"] == video
        job.assert_awaited_once_with("user-123", "t1", "aircAruvnKk")

    @pytest.mark.asyncio
    async def test_bad_url_is_400(self, headers):
        with patch("app.routers.videos._topic_service.get_topic", AsyncMock(return_value={})):
            from app.main import app

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/api/topic/t1/video", json={"url": "https://example.com"}, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_in_progress_is_409(self, headers):
        with (
            patch("app.routers.videos._topic_service.get_topic", AsyncMock(return_value={})),
            patch("app.routers.videos.get_video", AsyncMock(return_value={"status": "embedding"})),
        ):
            from app.main import app

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/api/topic/t1/video", json={"url": "aircAruvnKk"}, headers=headers)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_status_404_when_missing(self, headers):
        with patch("app.routers.videos.get_video", AsyncMock(return_value=None)):
            from app.main import app

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/videos/aircAruvnKk", headers=headers)
        assert resp.status_code == 404
