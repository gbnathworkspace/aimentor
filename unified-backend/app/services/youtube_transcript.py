"""Fetch a YouTube video's full transcript with timestamps.

Primary path: the video's captions via youtube-transcript-api (manual
captions preferred over auto-generated, English preferred, otherwise any
language). Fallback when a video has no captions: download its audio with
yt-dlp and transcribe it with OpenAI's Whisper API — only when
OPENAI_API_KEY is set, since running Whisper locally doesn't fit the 1 GB
production VM.

YouTube often blocks transcript requests from cloud IPs (Fly.io included).
YOUTUBE_PROXY_URL, when set, routes both paths through that proxy.

Everything here is blocking I/O; callers run it in a thread.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_PATTERNS = [
    re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/|v/))([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
]

# Whisper API rejects uploads over 25 MB.
_WHISPER_MAX_BYTES = 25 * 1024 * 1024


class TranscriptUnavailable(Exception):
    """No transcript could be produced. The message is safe to show the user."""


@dataclass(frozen=True)
class Segment:
    text: str
    start: float  # seconds
    duration: float


@dataclass(frozen=True)
class Transcript:
    segments: list[Segment]
    language: str
    source: str  # "captions" | "auto_captions" | "whisper"


def parse_video_id(url_or_id: str) -> str | None:
    """Return the 11-char YouTube video id from a URL or bare id, else None."""
    value = (url_or_id or "").strip()
    if _VIDEO_ID_RE.match(value):
        return value
    for pattern in _URL_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)
    return None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _proxy_url() -> str | None:
    return get_settings().YOUTUBE_PROXY_URL or None


def fetch_title(video_id: str) -> str | None:
    """Video title via YouTube's public oEmbed endpoint (no API key)."""
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": canonical_url(video_id), "format": "json"},
            proxy=_proxy_url(),
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("title")
    except Exception as e:
        logger.warning("oEmbed title lookup failed for %s: %s", video_id, e)
    return None


def fetch_captions(video_id: str) -> Transcript | None:
    """Full caption track, or None if the video has no captions at all.

    Raises TranscriptUnavailable for errors a retry won't fix (video
    private/removed) or that the user should hear about (IP blocked).
    """
    from youtube_transcript_api import (
        IpBlocked,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi,
    )
    from youtube_transcript_api.proxies import GenericProxyConfig

    proxy = _proxy_url()
    api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(https_url=proxy) if proxy else None)

    try:
        listing = list(api.list(video_id))
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except VideoUnavailable:
        raise TranscriptUnavailable("This video is unavailable (private, removed or region-locked).")
    except (RequestBlocked, IpBlocked):
        raise TranscriptUnavailable(
            "YouTube blocked the transcript request from this server. "
            "Set YOUTUBE_PROXY_URL to a residential proxy to fix this."
        )

    if not listing:
        return None

    def rank(t) -> tuple[int, int]:
        is_english = t.language_code.split("-")[0] == "en"
        return (0 if is_english else 1, 1 if t.is_generated else 0)

    best: Transcript | None = None
    # Usually the first track is the answer. When it is sparse (e.g. English
    # auto-captions on a Tamil video), try up to two other tracks and keep
    # the one with the most text.
    for chosen in sorted(listing, key=rank)[:3]:
        try:
            fetched = chosen.fetch()
        except Exception as e:
            logger.warning("Caption track %s failed for %s: %s", chosen.language_code, video_id, e)
            continue
        segments = [
            Segment(text=s.text.replace("\n", " ").strip(), start=float(s.start), duration=float(s.duration))
            for s in fetched.snippets
            if s.text and s.text.strip()
        ]
        if not segments:
            continue
        candidate = Transcript(
            segments=segments,
            language=chosen.language_code,
            source="auto_captions" if chosen.is_generated else "captions",
        )
        if best is None or transcript_chars(candidate) > transcript_chars(best):
            best = candidate
        if not is_sparse(best):
            break
    return best


def transcribe_audio(video_id: str) -> Transcript:
    """Fallback: yt-dlp audio download + OpenAI Whisper API transcription."""
    api_key = get_settings().OPENAI_API_KEY
    if not api_key:
        raise TranscriptUnavailable(
            "This video has no captions, so its transcript can't be read yet. "
            "Try a video with captions (the CC button on YouTube)."
        )

    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            # Smallest audio-only stream; no ffmpeg post-processing needed,
            # Whisper accepts webm/m4a as-is.
            "format": "worstaudio[ext=webm]/worstaudio[ext=m4a]/worstaudio",
            "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        if _proxy_url():
            opts["proxy"] = _proxy_url()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(canonical_url(video_id), download=True)
                path = ydl.prepare_filename(info)
        except Exception as e:
            raise TranscriptUnavailable(f"Could not download the video's audio: {e}")

        size = os.path.getsize(path)
        if size > _WHISPER_MAX_BYTES:
            raise TranscriptUnavailable(
                f"The video's audio is {size // (1024 * 1024)} MB, over Whisper's 25 MB limit."
            )

        with open(path, "rb") as audio:
            resp = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": "whisper-1", "response_format": "verbose_json"},
                files={"file": (os.path.basename(path), audio)},
                timeout=600,
            )
        if resp.status_code != 200:
            raise TranscriptUnavailable(f"Whisper transcription failed ({resp.status_code}).")
        body = resp.json()

    segments = [
        Segment(text=s["text"].strip(), start=float(s["start"]), duration=float(s["end"]) - float(s["start"]))
        for s in body.get("segments", [])
        if s.get("text", "").strip()
    ]
    if not segments:
        raise TranscriptUnavailable("Whisper returned an empty transcript.")
    return Transcript(segments=segments, language=body.get("language", ""), source="whisper")


# Speech runs ~800-1000 characters a minute; far below this the captions
# are mostly missing or garbage (wrong-language auto-captions).
_SPARSE_CHARS_PER_MINUTE = 250


def transcript_chars(transcript: Transcript) -> int:
    return sum(len(s.text) for s in transcript.segments)


def is_sparse(transcript: Transcript) -> bool:
    last = transcript.segments[-1]
    minutes = max((last.start + last.duration) / 60, 1)
    return transcript_chars(transcript) / minutes < _SPARSE_CHARS_PER_MINUTE


def fetch_transcript(video_id: str) -> Transcript:
    """Captions if the video has any, otherwise the Whisper fallback.
    Sparse captions also try Whisper when it is set up, keeping the captions
    if that fails."""
    transcript = fetch_captions(video_id)
    if transcript is not None:
        if is_sparse(transcript) and get_settings().OPENAI_API_KEY:
            logger.info("Captions for %s look sparse, trying audio transcription", video_id)
            try:
                return transcribe_audio(video_id)
            except TranscriptUnavailable as e:
                logger.warning("Whisper fallback failed for %s: %s", video_id, e)
        return transcript
    logger.info("No captions for %s, falling back to audio transcription", video_id)
    return transcribe_audio(video_id)
