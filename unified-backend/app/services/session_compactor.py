"""SessionCompactor — turns a closed (or forcibly-closed) session's messages
into a SummaryBlock, prunes the raw messages it just covered, and keeps a
topic's SummaryBlocks bounded via oldest-pair merging.

Replaces the old compaction_service.py + session_summarizer.py split: those
two ran on different triggers (mid-turn token-budget crossing vs. session
close) but wrote overlapping, uncoordinated state (an inline rolling summary
inside topic.messages vs. a separate topic.summaryBlocks array), and only
compaction_service ever reclaimed tokens by removing raw messages.

session_compactor runs at session boundaries only (session_boundary.py):
idle-gap close, idle sweep, logout/checkpoint, or a hard-ceiling force-close
for one session that's grown too large without ever going idle. There is no
mid-turn trigger — topic_chat_service no longer checks or triggers this
per turn.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from app.config.database import compaction_events_col, skill_graph_col, topics_col
from app.config.settings import get_settings
from app.models.skill import SubtopicMasteryUpdate
from app.services.llm_trace import traced_messages_create
from app.services.profiling_agent import propose_changes as propose_profile_changes
from app.services.token_counter import TokenCounter
from app.services.vector_search import delete_vectors, embed_and_upsert

logger = logging.getLogger(__name__)

MAX_SKILL_UPDATE_RETRIES = 3
"""Maximum retry attempts for skill graph updates."""

MAX_TAUGHT_CONCEPTS = 30
"""Cap on skill_graph's stored taught_concepts list — oldest dropped past this."""

BLOCK_WORD_CAP = 500
"""Max total word count across a topic's SummaryBlocks before merging kicks in."""

BLOCK_WORD_FLOOR = 50
"""Min word count a single SummaryBlock may be compressed to when merging."""

MAX_MERGE_PASSES_PER_CLOSE = 3
"""Max number of oldest-pair merges attempted per session-close."""

_LLM_TIMEOUT_SECONDS = 30
_SUMMARIZATION_MODEL = "claude-haiku-4-5-20251001"

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_COMPACTION_PROMPT_FILE = "compaction_summarize.md"
_MERGE_PROMPT_FILE = "session_merge.md"

_token_counter = TokenCounter()
_in_progress: set[str] = set()
"""Concurrency guard against overlapping close_session calls on the same topic."""

_COMPACTION_TOOL_SCHEMA = {
    "name": "compaction_result",
    "description": "Summarize the conversation excerpt and extract any skill updates",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A concise narrative summary (3-5 sentences) of the learning discussion",
            },
            "skill_updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subtopic": {"type": "string"},
                        "mastery": {"type": "number", "minimum": 0, "maximum": 100},
                    },
                    "required": ["subtopic", "mastery"],
                },
                "description": (
                    "Mastery (0-100) for only the specific subtopics OF THE CURRENT TOPIC "
                    "(given above) this excerpt gives real evidence about — do not guess at "
                    "subtopics not discussed, and never invent a subtopic name that isn't "
                    "actually part of this topic. Empty array if no progress detected."
                ),
            },
            "taught_concepts": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Specific things the mentor taught in this excerpt, one concise "
                    "entry per concept — e.g. 'Signed URLs/Cookies in CloudFront using "
                    "the direct-URL method'. Only concepts actually explained, not ones "
                    "merely mentioned in passing. Empty array if nothing new was taught."
                ),
            },
            "profile_signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": ["style_note"]},
                        "proposed_value": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": ["pacing", "communication", "motivation", "misconception", "context"],
                                },
                                "note": {"type": "string"},
                            },
                            "required": ["category", "note"],
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["field", "proposed_value", "reason"],
                },
                "description": (
                    "Clear signals about how this student learns best or what "
                    "motivates them, grounded in this excerpt. Only include a signal "
                    "with real, specific evidence — return an empty array if nothing "
                    "stands out. Do NOT force a signal every time."
                ),
            },
        },
        "required": ["summary", "skill_updates", "taught_concepts", "profile_signals"],
    },
}


def _word_count(text: str) -> int:
    return len(text.split())


def _load_prompt(filename: str) -> str:
    filepath = _PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Prompt template not found: {filepath}")
    return filepath.read_text(encoding="utf-8")


def _format_conversation_excerpt(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


async def _validate_skill_updates(topic_title: str, skill_updates: list) -> list[SubtopicMasteryUpdate]:
    """Validate raw (subtopic, mastery) pairs against topic_title's canonical
    subtopic list — topic_title is always the one this close_session call is
    already scoped to, never a string the LLM invents itself."""
    from app.services.subtopic_weights import validate_subtopic_updates

    if not topic_title or not isinstance(skill_updates, list) or not skill_updates:
        return []
    return await validate_subtopic_updates(topic_title, skill_updates)


async def _parse_tool_use_response(response, topic_title: str) -> dict:
    tool_input = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "compaction_result":
            tool_input = block.input
            break

    if tool_input is None:
        logger.error("LLM response did not contain expected tool_use block")
        raise ValueError("LLM response missing compaction_result tool call")

    summary = tool_input.get("summary", "")
    if not isinstance(summary, str) or not summary.strip():
        logger.error("LLM returned empty or invalid summary")
        raise ValueError("LLM returned empty summary")

    raw_skill_updates = tool_input.get("skill_updates", [])
    if not isinstance(raw_skill_updates, list):
        raw_skill_updates = []
    validated_updates = await _validate_skill_updates(topic_title, raw_skill_updates)

    raw_taught_concepts = tool_input.get("taught_concepts", [])
    if not isinstance(raw_taught_concepts, list):
        raw_taught_concepts = []
    taught_concepts = [c.strip() for c in raw_taught_concepts if isinstance(c, str) and c.strip()]

    raw_profile_signals = tool_input.get("profile_signals", [])
    if not isinstance(raw_profile_signals, list):
        raw_profile_signals = []

    return {
        "summary": summary.strip(),
        "skill_updates": validated_updates if validated_updates else None,
        "taught_concepts": taught_concepts,
        "profile_signals": raw_profile_signals,
    }


async def _call_summarization_llm(messages: list[dict], topic_title: str) -> dict:
    """Call Claude to summarize a run of session messages and extract skill
    updates, taught concepts, and profile signals via tool_use."""
    conversation_excerpt = _format_conversation_excerpt(messages)
    prompt_template = _load_prompt(_COMPACTION_PROMPT_FILE)
    prompt_text = (
        prompt_template
        .replace("{{topic}}", topic_title or "General")
        .replace("{{conversation}}", conversation_excerpt)
    )

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await asyncio.wait_for(
            traced_messages_create(
                client, call_site="session_compactor._call_summarization_llm",
                model=_SUMMARIZATION_MODEL,
                max_tokens=1024,
                tools=[_COMPACTION_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "compaction_result"},
                messages=[{"role": "user", "content": prompt_text}],
            ),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Session summarization LLM call timed out after %ds", _LLM_TIMEOUT_SECONDS)
        raise
    except Exception as e:
        logger.error("Session summarization LLM call failed: %s", str(e))
        raise

    return await _parse_tool_use_response(response, topic_title)


async def _call_merge_two_blocks_llm(text_a: str, text_b: str) -> str:
    """Combine two already-summarized SummaryBlocks into one, targeting
    roughly half their combined word count but never below BLOCK_WORD_FLOOR."""
    target_words = max(BLOCK_WORD_FLOOR, (_word_count(text_a) + _word_count(text_b)) // 2)
    prompt = (
        _load_prompt(_MERGE_PROMPT_FILE)
        .replace("{{target_words}}", str(target_words))
        .replace("{{floor_words}}", str(BLOCK_WORD_FLOOR))
        .replace("{{summary_a}}", text_a)
        .replace("{{summary_b}}", text_b)
    )

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await asyncio.wait_for(
        traced_messages_create(
            client, call_site="session_compactor._call_merge_two_blocks_llm",
            model=_SUMMARIZATION_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ),
        timeout=_LLM_TIMEOUT_SECONDS,
    )
    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    merged = "".join(text_blocks).strip()
    if not merged:
        raise ValueError("Merge LLM call returned empty text")
    return merged


async def enforce_word_cap(blocks: list[dict]) -> list[dict]:
    """Repeatedly merge the two oldest blocks (by createdAt) while total word
    count exceeds BLOCK_WORD_CAP, up to MAX_MERGE_PASSES_PER_CLOSE times or
    until fewer than 2 blocks remain. A failed merge stops the loop early and
    leaves blocks as they were before that attempt — never loses a block."""
    blocks = list(blocks)
    attempts = 0

    while (
        sum(b["wordCount"] for b in blocks) > BLOCK_WORD_CAP
        and len(blocks) >= 2
        and attempts < MAX_MERGE_PASSES_PER_CLOSE
    ):
        attempts += 1
        ordered = sorted(blocks, key=lambda b: b["createdAt"])
        a, b = ordered[0], ordered[1]

        try:
            merged_text = await _call_merge_two_blocks_llm(a["text"], b["text"])
        except Exception as e:
            logger.error("Session block merge failed: %s", str(e))
            break

        merged_block = {
            "blockId": str(uuid.uuid4()),
            "sourceSessionIds": list(dict.fromkeys(a["sourceSessionIds"] + b["sourceSessionIds"])),
            "text": merged_text,
            "wordCount": _word_count(merged_text),
            "mergeDepth": max(a["mergeDepth"], b["mergeDepth"]) + 1,
            "createdAt": min(a["createdAt"], b["createdAt"]),
            "lastMergedAt": datetime.now(timezone.utc),
        }

        remaining = [blk for blk in blocks if blk["blockId"] not in (a["blockId"], b["blockId"])]
        blocks = remaining + [merged_block]

    return blocks


async def _apply_skill_updates(
    user_id: str, topic_title: str, skill_updates: list[SubtopicMasteryUpdate]
) -> None:
    """Apply extracted skill updates to the skill graph, with retries. On
    permanent failure, logs for operator review but never raises — the
    summary block this rides alongside is preserved regardless."""
    from app.services.skill_graph_repo import apply_update

    for attempt in range(MAX_SKILL_UPDATE_RETRIES):
        try:
            await apply_update(user_id, topic_title, skill_updates)
            return
        except Exception as e:
            logger.error(
                "Skill update attempt %d failed for user %s: %s", attempt + 1, user_id, str(e),
            )
            if attempt == MAX_SKILL_UPDATE_RETRIES - 1:
                logger.error(
                    "Skill update permanently failed after %d attempts for user %s — discarding.",
                    MAX_SKILL_UPDATE_RETRIES, user_id,
                )


async def _apply_taught_concepts(topic_title: str, user_id: str, new_concepts: list[str]) -> None:
    """Append newly-taught concepts onto the skill_graph node's
    `taught_concepts` list — an L3 (episodic memory) record, concept-grained
    rather than narrative-grained. Lives on skill_graph (keyed by
    user_id+topic title) alongside the rest of "what does this user know
    about this topic" — unlike SummaryBlocks, it isn't tied to one topic
    thread's message history. Deduplicated, capped at MAX_TAUGHT_CONCEPTS
    (oldest dropped first), upserted since a topic can reach this before any
    skill_graph document exists for it. Best-effort: a failure here never
    blocks the write it rides alongside."""
    try:
        skill = await skill_graph_col().find_one(
            {"user_id": user_id, "topic": topic_title}, {"_id": 0, "taught_concepts": 1},
        )
        existing = (skill or {}).get("taught_concepts") or []
        merged = existing + [c for c in new_concepts if c not in existing]
        merged = merged[-MAX_TAUGHT_CONCEPTS:]
        await skill_graph_col().update_one(
            {"user_id": user_id, "topic": topic_title},
            {"$set": {"taught_concepts": merged}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(
            "Failed to persist taught_concepts for topic=%s user=%s: %s", topic_title, user_id, e,
        )


async def close_session(topic_id: str, user_id: str, upto_timestamp: datetime) -> None:
    """Summarize the run of not-yet-covered messages up to `upto_timestamp`
    into a fresh SummaryBlock, apply skill_updates/taught_concepts/profile
    signals, enforce the word cap, and prune the raw messages just covered
    out of topic.messages so they stop counting against the topic's token
    budget. No-op if no uncovered messages exist — safe to call repeatedly
    (idle sweep, logout, browser-close checkpoint, and a hard-ceiling force
    close can all reach the same topic).
    """
    if topic_id in _in_progress:
        return
    _in_progress.add(topic_id)
    try:
        await _close_session(topic_id, user_id, upto_timestamp)
    finally:
        _in_progress.discard(topic_id)


async def _close_session(topic_id: str, user_id: str, upto_timestamp: datetime) -> None:
    topic = await topics_col().find_one({"topicId": topic_id, "userId": user_id})
    if not topic:
        return

    existing_blocks = topic.get("summaryBlocks") or []
    covered_ids = {mid for blk in existing_blocks for mid in blk.get("sourceSessionIds", [])}

    all_messages = topic.get("messages", [])
    session_messages = [
        m for m in all_messages
        if m.get("type") == "message"
        and m.get("id") not in covered_ids
        and m.get("timestamp") <= upto_timestamp
    ]
    if not session_messages:
        return

    try:
        llm_result = await _call_summarization_llm(session_messages, topic.get("title", ""))
    except Exception as e:
        logger.error("Session summarization LLM call failed for topic %s: %s", topic_id, str(e))
        return

    skill_updates = llm_result.get("skill_updates")
    if skill_updates:
        await _apply_skill_updates(user_id, topic.get("title", ""), skill_updates)

    taught_concepts = llm_result.get("taught_concepts")
    if taught_concepts:
        await _apply_taught_concepts(topic.get("title", ""), user_id, taught_concepts)

    profile_signals = llm_result.get("profile_signals")
    if profile_signals:
        await propose_profile_changes(user_id, topic_id, profile_signals)

    summary_text = llm_result["summary"]
    covered_message_ids = {m["id"] for m in session_messages}
    new_block = {
        "blockId": str(uuid.uuid4()),
        "sourceSessionIds": list(covered_message_ids),
        "text": summary_text,
        "wordCount": _word_count(summary_text),
        "mergeDepth": 0,
        "createdAt": session_messages[0]["timestamp"],
        "lastMergedAt": datetime.now(timezone.utc),
    }

    new_blocks = await enforce_word_cap(existing_blocks + [new_block])

    # Prune the raw messages just covered — this is the token-reclamation
    # step the old session_summarizer never did. Anything not of type
    # "message" (e.g. a legacy inline rolling-summary block from before this
    # merge) is left untouched; it's read as a historical fallback only.
    pruned_messages = [
        m for m in all_messages
        if not (m.get("type") == "message" and m.get("id") in covered_message_ids)
    ]

    tokens_before = _token_counter.count_window(all_messages)
    new_token_estimate = _token_counter.count_window(pruned_messages)

    current_version = topic.get("version", 0)
    result = await topics_col().update_one(
        {"topicId": topic_id, "userId": user_id, "version": current_version},
        {
            "$set": {
                "messages": pruned_messages,
                "summaryBlocks": new_blocks,
                "metadata.currentTokenEstimate": new_token_estimate,
                "version": current_version + 1,
            },
        },
    )
    if result.modified_count != 1:
        logger.error("Session close failed: concurrent write conflict for topic %s", topic_id)
        return

    event_id = str(uuid.uuid4())
    await compaction_events_col().insert_one({
        "eventId": event_id,
        "topicId": topic_id,
        "userId": user_id,
        "timestamp": datetime.now(timezone.utc),
        "messagesCompacted": len(session_messages),
        "tokensBeforeCompaction": tokens_before,
        "tokensAfterCompaction": new_token_estimate,
        "tokensReclaimed": tokens_before - new_token_estimate,
        "skillUpdateGenerated": bool(skill_updates),
        "skillUpdate": [u.model_dump() for u in skill_updates] if skill_updates else None,
        "summaryBlockId": new_block["blockId"],
    })

    # Best-effort, fire-and-forget: keep vector search in sync with the
    # blocks that just changed. Never blocks or fails close_session itself.
    asyncio.create_task(_sync_block_embeddings(topic_id, user_id, existing_blocks, new_blocks))


async def _sync_block_embeddings(
    topic_id: str, user_id: str, old_blocks: list[dict], new_blocks: list[dict]
) -> None:
    """Embed newly-created/merged blocks, delete embeddings for blocks that
    got merged away. Diffed by blockId so an unchanged block is never
    re-embedded (Voyage calls cost money and time)."""
    old_ids = {b["blockId"] for b in old_blocks}
    new_ids = {b["blockId"] for b in new_blocks}

    stale_ids = old_ids - new_ids
    if stale_ids:
        await delete_vectors(list(stale_ids))

    for block in new_blocks:
        if block["blockId"] in old_ids:
            continue
        await embed_and_upsert(
            vector_id=block["blockId"],
            text=block["text"],
            user_id=user_id,
            source="summary_block",
            metadata={"topic_id": topic_id, "block_id": block["blockId"]},
        )
