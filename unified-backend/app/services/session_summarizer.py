"""SessionSummarizer — turns a closed session's messages into a SummaryBlock,
and keeps a topic's SummaryBlocks bounded via oldest-pair merging.

See .kiro/specs/session-narrative-summary. Reuses CompactionService's LLM
summarization/skill-update/taught-concept plumbing rather than duplicating it.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from app.config.database import topics_col
from app.config.settings import get_settings
from app.services.llm_trace import traced_messages_create
from app.services.compaction_service import (
    CompactionService,
    _LLM_TIMEOUT_SECONDS,
    _SUMMARIZATION_MODEL,
)
from app.services.profiling_agent import propose_changes as propose_profile_changes
from app.services.vector_search import delete_vectors, embed_and_upsert

logger = logging.getLogger(__name__)

BLOCK_WORD_CAP = 500
"""Max total word count across a topic's SummaryBlocks before merging kicks in."""

BLOCK_WORD_FLOOR = 50
"""Min word count a single SummaryBlock may be compressed to when merging."""

MAX_MERGE_PASSES_PER_CLOSE = 3
"""Max number of oldest-pair merges attempted per session-close."""

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_MERGE_PROMPT_FILE = "session_merge.md"

_compaction_service = CompactionService()


def _word_count(text: str) -> int:
    return len(text.split())


def _load_merge_prompt() -> str:
    filepath = _PROMPTS_DIR / _MERGE_PROMPT_FILE
    if not filepath.exists():
        raise FileNotFoundError(f"Session merge prompt template not found: {filepath}")
    return filepath.read_text(encoding="utf-8")


async def _call_merge_two_blocks_llm(text_a: str, text_b: str) -> str:
    """Combine two already-summarized SummaryBlocks into one, targeting
    roughly half their combined word count but never below BLOCK_WORD_FLOOR
    (Requirement 3.4)."""
    target_words = max(BLOCK_WORD_FLOOR, (_word_count(text_a) + _word_count(text_b)) // 2)
    prompt = (
        _load_merge_prompt()
        .replace("{{target_words}}", str(target_words))
        .replace("{{floor_words}}", str(BLOCK_WORD_FLOOR))
        .replace("{{summary_a}}", text_a)
        .replace("{{summary_b}}", text_b)
    )

    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await asyncio.wait_for(
        traced_messages_create(
            client, call_site="session_summarizer._call_merge_two_blocks_llm",
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
    until fewer than 2 blocks remain (Requirement 3.1, 3.2, 3.5, 3.6).

    A failed merge stops the loop early and leaves blocks as they were before
    that attempt (Error Scenario 2) — never loses a block's content.
    """
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


async def close_session(topic_id: str, user_id: str, upto_timestamp: datetime) -> None:
    """Summarize the run of messages since the last close point into a fresh
    SummaryBlock, apply skill_updates/taught_concepts, and enforce the word
    cap. No-op if no uncovered messages exist (Requirement 1.5)."""
    topic = await topics_col().find_one({"topicId": topic_id, "userId": user_id})
    if not topic:
        return

    existing_blocks = topic.get("summaryBlocks") or []
    covered_ids = {mid for blk in existing_blocks for mid in blk.get("sourceSessionIds", [])}

    session_messages = [
        m for m in topic.get("messages", [])
        if m.get("type") == "message"
        and m.get("id") not in covered_ids
        and m.get("timestamp") <= upto_timestamp
    ]
    if not session_messages:
        return

    try:
        llm_result = await _compaction_service._call_summarization_llm(
            session_messages, topic.get("title", "")
        )
    except Exception as e:
        logger.error("Session summarization LLM call failed for topic %s: %s", topic_id, str(e))
        return

    skill_updates = llm_result.get("skill_updates")
    if skill_updates:
        await _compaction_service._apply_skill_updates(user_id, topic.get("title", ""), skill_updates)

    taught_concepts = llm_result.get("taught_concepts")
    if taught_concepts:
        await _compaction_service._apply_taught_concepts(topic.get("title", ""), user_id, taught_concepts)

    profile_signals = llm_result.get("profile_signals")
    if profile_signals:
        await propose_profile_changes(user_id, topic_id, profile_signals)

    summary_text = llm_result["summary"]
    new_block = {
        "blockId": str(uuid.uuid4()),
        "sourceSessionIds": [m["id"] for m in session_messages],
        "text": summary_text,
        "wordCount": _word_count(summary_text),
        "mergeDepth": 0,
        "createdAt": session_messages[0]["timestamp"],
        "lastMergedAt": datetime.now(timezone.utc),
    }

    new_blocks = await enforce_word_cap(existing_blocks + [new_block])

    current_version = topic.get("version", 0)
    result = await topics_col().update_one(
        {"topicId": topic_id, "userId": user_id, "version": current_version},
        {"$set": {"summaryBlocks": new_blocks, "version": current_version + 1}},
    )
    if result.modified_count != 1:
        logger.error(
            "Session close failed: concurrent write conflict for topic %s", topic_id
        )
        return

    # Best-effort, fire-and-forget: keep vector search in sync with the
    # blocks that just changed. Never blocks or fails close_session itself.
    asyncio.create_task(
        _sync_block_embeddings(topic_id, user_id, existing_blocks, new_blocks)
    )


async def _sync_block_embeddings(
    topic_id: str, user_id: str, old_blocks: list[dict], new_blocks: list[dict]
) -> None:
    """Embed newly-created/merged blocks, delete embeddings for blocks that
    got merged away. Diffed by blockId so an unchanged block is never
    re-embedded (Voyage calls cost money and time).
    """
    old_ids = {b["blockId"] for b in old_blocks}
    new_ids = {b["blockId"] for b in new_blocks}

    stale_ids = old_ids - new_ids
    if stale_ids:
        await delete_vectors(list(stale_ids))

    for block in new_blocks:
        if block["blockId"] in old_ids:
            continue  # unchanged, already embedded
        await embed_and_upsert(
            vector_id=block["blockId"],
            text=block["text"],
            user_id=user_id,
            source="summary_block",
            metadata={"topic_id": topic_id, "block_id": block["blockId"]},
        )
