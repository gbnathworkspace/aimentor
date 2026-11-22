"""YouTube video ingest: full transcript -> overlapping chunks -> embeddings.

Runs as a background task. The whole transcript is chunked with the same
chunker as uploaded documents (1000 chars, 200 overlap) and every chunk is
stored in `embeddings` with metadata.source="video_transcript", so the
mentor's search_documents tool finds it. Each chunk keeps the start/end
second of the video it covers.

A `videos` record (one per user + video) tracks title, URL and status so the
frontend can poll progress. Only a short LLM summary of the video goes to L3
memory (an embeddings row with source="summary_block", like session summary
blocks); the transcript itself never does.

Status flow: queued -> fetching -> embedding -> summarizing -> completed,
or failed with `error` set at any step.
"""

from __future__ import annotations

import asyncio
import bisect
import logging
from datetime import datetime, timezone

import anthropic

from app.config.database import embeddings_col, videos_col
from app.config.settings import get_settings
from app.services.embedder import embed_texts
from app.services.extraction import chunk_spans
from app.services.llm_trace import traced_messages_create
from app.services.vector_search import embed_and_upsert
from app.services.youtube_transcript import (
    Segment,
    TranscriptUnavailable,
    canonical_url,
    fetch_title,
    fetch_transcript,
)

logger = logging.getLogger(__name__)

VIDEO_SOURCE = "video_transcript"
_SUMMARY_MODEL = "claude-haiku-4-5-20251001"
# ~40k tokens: plenty for a summary, and keeps a 3-hour lecture affordable.
_SUMMARY_INPUT_CHARS = 160_000

_PUBLIC_FIELDS = {
    "_id": 0, "video_id": 1, "topic_id": 1, "url": 1, "title": 1, "status": 1,
    "transcript_source": 1, "language": 1, "duration_seconds": 1,
    "chunk_count": 1, "summary": 1, "error": 1, "created_at": 1, "updated_at": 1,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_timed_chunks(segments: list[Segment]) -> list[dict]:
    """Join transcript segments into one text, chunk it, and give each chunk
    the start/end time of the segments it overlaps."""
    if not segments:
        return []

    parts: list[str] = []
    offsets: list[int] = []
    pos = 0
    for seg in segments:
        offsets.append(pos)
        parts.append(seg.text)
        pos += len(seg.text) + 1  # +1 for the joining space
    text = " ".join(parts)

    chunks = []
    for start_char, end_char in chunk_spans(text):
        chunk = text[start_char:end_char].strip()
        if not chunk:
            continue
        first = max(bisect.bisect_right(offsets, start_char) - 1, 0)
        last = max(bisect.bisect_right(offsets, max(end_char - 1, start_char)) - 1, first)
        chunks.append({
            "text": chunk,
            "start_seconds": round(segments[first].start, 2),
            "end_seconds": round(segments[last].start + segments[last].duration, 2),
        })
    return chunks


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


async def _set(user_id: str, video_id: str, **fields) -> None:
    await videos_col().update_one(
        {"user_id": user_id, "video_id": video_id},
        {"$set": {**fields, "updated_at": _now()}},
    )


async def create_video_job(user_id: str, topic_id: str, video_id: str) -> dict:
    """Create (or reset, on re-submit) the videos record in status=queued."""
    now = _now()
    await videos_col().update_one(
        {"user_id": user_id, "video_id": video_id},
        {
            "$set": {
                "topic_id": topic_id, "url": canonical_url(video_id), "status": "queued",
                "error": None, "updated_at": now,
            },
            "$setOnInsert": {"user_id": user_id, "video_id": video_id, "created_at": now},
        },
        upsert=True,
    )
    return await get_video(user_id, video_id)


async def get_video(user_id: str, video_id: str) -> dict | None:
    return await videos_col().find_one({"user_id": user_id, "video_id": video_id}, _PUBLIC_FIELDS)


async def list_topic_videos(user_id: str, topic_id: str) -> list[dict]:
    cursor = videos_col().find({"user_id": user_id, "topic_id": topic_id}, _PUBLIC_FIELDS)
    return await cursor.sort("created_at", -1).to_list(length=100)


async def delete_video(user_id: str, video_id: str) -> bool:
    """Remove the video record, its transcript chunks and its L3 summary."""
    result = await videos_col().delete_one({"user_id": user_id, "video_id": video_id})
    await embeddings_col().delete_many({"user_id": user_id, "metadata.video_id": video_id})
    return result.deleted_count > 0


async def _summarize(title: str | None, transcript_text: str, user_id: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=get_settings().ANTHROPIC_API_KEY)
    response = await traced_messages_create(
        client,
        call_site="video_ingest._summarize",
        user_id=user_id,
        model=_SUMMARY_MODEL,
        max_tokens=400,
        system=(
            "You summarize a YouTube video's transcript for a learner's memory. "
            "Write 3-5 plain sentences: what the video teaches and its key ideas. "
            "No preamble, no bullet points."
        ),
        messages=[{
            "role": "user",
            "content": f"Title: {title or 'unknown'}\n\nTranscript:\n{transcript_text[:_SUMMARY_INPUT_CHARS]}",
        }],
    )
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()


async def run_video_ingest(user_id: str, topic_id: str, video_id: str) -> None:
    """Background job: fetch, chunk, embed and store one video's transcript."""
    try:
        await _set(user_id, video_id, status="fetching")
        title = await asyncio.to_thread(fetch_title, video_id)
        transcript = await asyncio.to_thread(fetch_transcript, video_id)
        last = transcript.segments[-1]
        await _set(
            user_id, video_id, title=title, transcript_source=transcript.source,
            language=transcript.language, duration_seconds=round(last.start + last.duration),
        )

        chunks = build_timed_chunks(transcript.segments)
        if not chunks:
            raise TranscriptUnavailable("The transcript is empty.")

        await _set(user_id, video_id, status="embedding", chunk_count=len(chunks))
        vectors = await embed_texts([c["text"] for c in chunks])
        if len(vectors) != len(chunks) or any(not v for v in vectors):
            raise RuntimeError("Voyage returned fewer embeddings than chunks")

        url = canonical_url(video_id)
        uploaded_at = _now()
        rows = [
            {
                "vector_id": f"video:{user_id}:{video_id}:{i}",
                "user_id": user_id,
                "text": c["text"],
                "embedding": vector,
                "metadata": {
                    "source": VIDEO_SOURCE, "video_id": video_id, "topic_id": topic_id,
                    "title": title, "url": url, "chunk_index": i,
                    "start_seconds": c["start_seconds"], "end_seconds": c["end_seconds"],
                    "uploaded_at": uploaded_at,
                },
            }
            for i, (c, vector) in enumerate(zip(chunks, vectors))
        ]
        # Re-submitting a video replaces its chunks rather than duplicating them.
        await embeddings_col().delete_many(
            {"user_id": user_id, "metadata.source": VIDEO_SOURCE, "metadata.video_id": video_id}
        )
        await embeddings_col().insert_many(rows)

        await _set(user_id, video_id, status="summarizing")
        summary = ""
        try:
            full_text = " ".join(s.text for s in transcript.segments)
            summary = await _summarize(title, full_text, user_id)
        except Exception:
            # The transcript is already searchable; a missing summary
            # shouldn't fail the whole job.
            logger.exception("Video summary failed for %s", video_id)

        if summary:
            await embed_and_upsert(
                vector_id=f"video_summary:{user_id}:{video_id}",
                text=f"Watched video \"{title or url}\": {summary}",
                user_id=user_id,
                source="summary_block",
                metadata={"topic_id": topic_id, "video_id": video_id, "kind": "video_summary"},
            )

        await _set(user_id, video_id, status="completed", summary=summary or None, error=None)
        logger.info("Video %s ingested: %d chunks", video_id, len(chunks))

    except TranscriptUnavailable as e:
        logger.warning("Video %s ingest failed: %s", video_id, e)
        await _set(user_id, video_id, status="failed", error=str(e))
    except Exception as e:
        logger.exception("Video %s ingest failed", video_id)
        await _set(user_id, video_id, status="failed", error=f"Processing failed: {e}")
