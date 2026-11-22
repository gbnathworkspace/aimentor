"""Mentor toolkit: the locally executed tools the mentor model can call,
as LangChain tools, plus one generic executor.

Per-turn state reaches every tool through a single injected `turn`
argument (InjectedToolArg), which LangChain keeps out of the schema sent to
the model. The model can never choose whose data a tool reads, even if a
prompt-injected document tells it to.

`web_search` isn't here: it's an Anthropic server tool with no local function.
See .kiro/specs/mentor-langchain-tools/design.md.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Annotated, Any

from langchain_core.tools import BaseTool, InjectedToolArg, tool

from app.services import prompt_store, skill_graph_repo
from app.services.llm_trace import write_trace
from app.services.subtopic_weights import validate_subtopic_updates
from app.services.topic_service import UNNAMED_TITLE
from app.services.vector_search import vector_search
from app.services.video_ingest import (
    VIDEO_SOURCE,
    create_video_job,
    format_timestamp,
    get_video,
    run_video_ingest,
)
from app.services.youtube_transcript import parse_video_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnState:
    user_id: str
    topic_title: str
    context: dict[str, Any] = field(default_factory=dict)
    topic_id: str | None = None


_SEARCH_DOCUMENTS_DESCRIPTION = (
    "Semantically search the user's uploaded documents (résumé, notes, "
    "problem lists) and the transcripts of YouTube videos they added, for a "
    "specific query. Video results start with the video title and timestamp. Use this when you need a "
    "detail that isn't already in the Uploaded Documents section — the "
    "default injection is a small unranked sample, not the full set."
)

_ADD_YOUTUBE_VIDEO_DESCRIPTION = (
    "Add a YouTube video to the user's knowledge: fetches its full "
    "transcript, stores it for search_documents, and returns the title, "
    "length and a short summary. Call this whenever the user shares a "
    "YouTube link and wants to learn from or discuss it, then use "
    "search_documents for details from the video."
)

_SEARCH_OTHER_TOPICS_DESCRIPTION = (
    "Semantically search the user's session history in OTHER topics "
    "for a specific query. Use this only when the user references "
    "something from a different topic that isn't already in your "
    "context — not for anything about the current topic (use "
    "get_past_sessions for that)."
)

_GET_USER_PROFILE_DESCRIPTION = (
    "Get the user's learning-context facts (background, goals, "
    "experience) and observed teaching-style notes. Call this if you "
    "need to tailor an explanation or example to who the user is or "
    "how they like to learn."
)

_GET_SKILL_STATE_DESCRIPTION = (
    "Get this topic's per-subtopic mastery levels and the specific "
    "concepts already taught in this topic. Call this before deciding "
    "how much to re-explain or how to calibrate difficulty."
)

_GET_PAST_SESSIONS_DESCRIPTION = (
    "Get narrative summaries of this topic's own prior closed sessions. "
    "Call this if the user references something discussed before in "
    "this topic, or you need continuity with earlier sessions here."
)

_RECORD_DIAGNOSTIC_VERDICT_DESCRIPTION = (
    "Record mastery for the specific subtopics the user's answers gave enough "
    "signal to judge, once you have that signal. Do not call this until you're "
    "confident on at least one subtopic — it's fine to ask another question "
    "first and call it on a later turn. Only include subtopics you actually "
    "assessed this turn; do not guess at the rest."
)

# A dict schema, not a Pydantic model: LangChain validates Pydantic
# args_schemas all-or-nothing, so one out-of-range item would reject the
# whole verdict. validate_subtopic_updates drops bad items individually.
_RECORD_DIAGNOSTIC_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "subtopic_updates": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "subtopic": {"type": "string"},
                    "mastery": {"type": "number", "minimum": 0, "maximum": 100},
                },
                "required": ["subtopic", "mastery"],
            },
        },
    },
    "required": ["subtopic_updates"],
}


def _format_result(result: dict) -> str:
    text = result.get("text", "")
    meta = result.get("metadata") or {}
    if meta.get("source") != VIDEO_SOURCE:
        return text
    start = meta.get("start_seconds") or 0
    header = (
        f"[Video: {meta.get('title') or meta.get('url')} @ "
        f"{format_timestamp(start)}-{format_timestamp(meta.get('end_seconds') or start)} "
        f"{meta.get('url')}&t={int(start)}s]"
    )
    return f"{header}\n{text}"


def _format_search_results(results: list[dict], empty_msg: str) -> str:
    if not results:
        return empty_msg
    return "\n\n".join(_format_result(r) for r in results)


@tool("search_documents", description=_SEARCH_DOCUMENTS_DESCRIPTION)
async def search_documents(query: str, turn: Annotated[TurnState, InjectedToolArg]) -> str:
    results = await vector_search(query, turn.user_id, source=["ingestion", VIDEO_SOURCE], limit=5)
    return _format_search_results(results, "No matching documents found.")


# How long a turn waits for a video ingest before telling the model it's
# still running (it carries on in the background either way). A 2-hour
# video with captions takes well under this.
_VIDEO_WAIT_SECONDS = 90


def _describe_video(video: dict) -> str:
    duration = video.get("duration_seconds")
    lines = [
        f"Video: {video.get('title') or video.get('url')}",
        f"Length: {format_timestamp(duration) if duration else 'unknown'}",
        f"Transcript chunks stored: {video.get('chunk_count') or 0}",
    ]
    if video.get("sparse"):
        lines.append(
            "WARNING: the video's captions are sparse or unreliable (often the "
            "wrong language), so the transcript is incomplete. Tell the user "
            "this and do not guess at what the video says."
        )
    if video.get("summary"):
        lines.append(f"Summary: {video['summary']}")
    lines.append("Use search_documents for specific details from this video.")
    return "\n".join(lines)


@tool("add_youtube_video", description=_ADD_YOUTUBE_VIDEO_DESCRIPTION)
async def add_youtube_video(url: str, turn: Annotated[TurnState, InjectedToolArg]) -> str:
    video_id = parse_video_id(url)
    if not video_id:
        return "That isn't a valid YouTube video link."
    if not turn.topic_id:
        return "Videos can only be added inside a topic."

    existing = await get_video(turn.user_id, video_id)
    if existing and existing.get("status") == "completed":
        return _describe_video(existing)
    if not existing or existing.get("status") == "failed":
        await create_video_job(turn.user_id, turn.topic_id, video_id)
        job = asyncio.create_task(run_video_ingest(turn.user_id, turn.topic_id, video_id))
        try:
            # shield: a timeout stops the wait, not the ingest.
            await asyncio.wait_for(asyncio.shield(job), _VIDEO_WAIT_SECONDS)
        except asyncio.TimeoutError:
            pass

    video = await get_video(turn.user_id, video_id) or {}
    status = video.get("status")
    if status == "completed":
        return _describe_video(video)
    if status == "failed":
        return f"Could not add the video: {video.get('error') or 'unknown error'}"
    return (
        "The video is still being processed (long video). Tell the user it "
        "will be searchable in a minute or two."
    )


# Cross-topic only: this topic's own history goes through get_past_sessions.
# The model has to choose to look, so nothing crosses topics silently.
@tool("search_other_topics", description=_SEARCH_OTHER_TOPICS_DESCRIPTION)
async def search_other_topics(query: str, turn: Annotated[TurnState, InjectedToolArg]) -> str:
    results = await vector_search(query, turn.user_id, source="summary_block", limit=5)
    return _format_search_results(results, "No matching past sessions found.")


@tool("get_user_profile", description=_GET_USER_PROFILE_DESCRIPTION)
async def get_user_profile(turn: Annotated[TurnState, InjectedToolArg]) -> str:
    profile = turn.context.get("profile", {})
    learning_context = prompt_store.format_learning_context(profile, turn.context.get("l1_scope"))
    style_notes = prompt_store.format_style_notes(profile.get("style_notes") or [])
    return f"Learning Context: {learning_context}\n\nTeaching style notes:\n{style_notes}"


@tool("get_skill_state", description=_GET_SKILL_STATE_DESCRIPTION)
async def get_skill_state(turn: Annotated[TurnState, InjectedToolArg]) -> str:
    skill = turn.context.get("skill", {})
    mastery = prompt_store.format_subtopic_mastery(skill.get("subtopic_mastery"))
    taught = prompt_store.format_taught_concepts(turn.context.get("taught_concepts"))
    return f"Subtopic Mastery:\n{mastery}\n\nAlready Taught In This Topic:\n{taught}"


@tool("get_past_sessions", description=_GET_PAST_SESSIONS_DESCRIPTION)
async def get_past_sessions(turn: Annotated[TurnState, InjectedToolArg]) -> str:
    return prompt_store.format_summary_blocks(turn.context.get("summary_blocks"))


@tool(
    "record_diagnostic_verdict",
    description=_RECORD_DIAGNOSTIC_VERDICT_DESCRIPTION,
    args_schema=_RECORD_DIAGNOSTIC_VERDICT_SCHEMA,
)
async def record_diagnostic_verdict(
    turn: Annotated[TurnState, InjectedToolArg],
    subtopic_updates: list | None = None,
    **_model_extras: Any,
) -> str:
    if turn.topic_title == UNNAMED_TITLE:
        # No real topic to file mastery under yet; the session-end summary
        # names the topic and records mastery under that name.
        return "Topic not named yet; mastery will be recorded at session end."
    validated = await validate_subtopic_updates(turn.topic_title, subtopic_updates or [])
    await skill_graph_repo.apply_update(turn.user_id, turn.topic_title, validated)
    return f"Recorded mastery for {len(validated)} subtopic(s)."


LOOP_TOOLS: list[BaseTool] = [
    search_documents, search_other_topics, get_user_profile, get_skill_state, get_past_sessions,
    add_youtube_video,
]
LOOP_TOOL_NAMES = frozenset(t.name for t in LOOP_TOOLS)
DIAGNOSTIC_VERDICT_TOOL: BaseTool = record_diagnostic_verdict

_TOOLS_BY_NAME = {t.name: t for t in [*LOOP_TOOLS, DIAGNOSTIC_VERDICT_TOOL]}


async def run_tool(name: str, args: dict, turn: TurnState) -> str:
    """Execute one model tool call with `turn` injected. Never raises: a
    failure returns fail-open text so the turn continues. Every execution
    is traced; only the model's own args go in the trace, never `turn`."""
    selected = _TOOLS_BY_NAME.get(name)
    if selected is None:
        return f"Unknown tool: {name}"

    start = time.monotonic()
    result, error = None, None
    try:
        # `turn` last, so a model-supplied "turn" key can't override it.
        result = await selected.ainvoke({**args, "turn": turn})
    except Exception as e:
        logger.warning("Tool %s failed for user=%s: %s", name, turn.user_id, e)
        error = str(e)

    await write_trace(
        f"mentor_tool.{name}", "", turn.user_id,
        json.dumps(args, ensure_ascii=False, default=str),
        response=result, error=error,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
    if error is not None:
        return f"Lookup failed for {name} — proceed without this information."
    return result
