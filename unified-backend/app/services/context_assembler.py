"""L1 + L2 + L3 context assembly for mentor chat.

Gathers the user's profile, skill node for the topic, and this topic's own
SummaryBlocks (session-narrative-summary spec) for L3. Implements graceful
degradation:
- Profile missing → HTTP 400 (onboarding required)
- Skill fetch fails → empty dict

Also provides `prepare_conversation_window` for topic-based conversations:
validates, orders, and budget-trims a mixed list of Messages and SummaryBlocks.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from app.services.token_budget import count_tokens

from app.config.database import (
    embeddings_col,
    profiles_col,
    skill_graph_col,
)

logger = logging.getLogger(__name__)

# ponytail: dump-all (capped), no vector search — onboarding uploads are a few
# chunks (résumé, problem list) tied to one user. Add vector ranking + the #5
# Atlas index only if uploads grow large/many.
_MAX_DOCUMENT_CHUNKS = 12


async def assemble(
    user_id: str, topic: str, query: str,
    topic_id: str | None = None,
    l1_scope: list[dict] | None = None,
    summary_blocks: list[dict] | None = None,
) -> dict:
    """Gather L1 profile, L2 skill, and L3 memory for the given user/topic.

    Args:
        user_id: The authenticated user's ID.
        topic: The current mentoring topic.
        query: The user's latest message. Currently unused — reserved for
            future semantic retrieval (issue #5).
        topic_id: The topic's id, used to fetch documents uploaded as
            context scoped to this topic (metadata.source="topic_document").
            None degrades to user-wide documents only, same as before.
        l1_scope: The topic's cached relevance judgments (see
            TopicService._ensure_l1_scope), if the caller has a topic
            document to read one from. Passed straight through to the
            returned dict — not fetched here, since assemble() only knows
            a topic title, not a topic id.
        summary_blocks: The topic's own `topic.summaryBlocks` (see
            session-narrative-summary spec) — one entry per closed session,
            this topic's sole narrative L3 source. Same pass-through-only
            treatment as l1_scope.

    Returns:
        A dict with keys: profile, skill, documents,
        l1_scope, taught_concepts, summary_blocks.

    Raises:
        HTTPException(400): If no profile exists for the user.
    """
    # L1 — Profile (required)
    profile = await profiles_col().find_one({"user_id": user_id}, {"_id": 0})
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile found. Please complete onboarding first.",
        )

    # L2 — Skill node (optional, degrade gracefully). `taught_concepts` (see
    # CompactionService._apply_taught_concepts, TS-1) lives on this same
    # document — an L3 episodic record, topic-scoped and concept-grained —
    # rather than on the topic itself, since it's "what this user knows
    # about this topic" state, not part of any one topic thread's history.
    try:
        skill = await skill_graph_col().find_one(
            {"user_id": user_id, "topic": topic}, {"_id": 0}
        )
    except Exception as e:
        logger.warning("Skill graph fetch failed for user=%s topic=%s: %s", user_id, topic, e)
        skill = None

    # Uploaded documents (résumé / LeetCode etc. ingested at onboarding),
    # plus this topic's own documents (see /topic/{id}/document), if any.
    # Without this read the ingest pipeline is orphaned — files embedded, never used (issue #4).
    documents = await _fetch_documents(user_id, topic_id)

    return {
        "profile": profile,
        "skill": skill or {},
        "documents": documents,
        "l1_scope": l1_scope,
        "taught_concepts": (skill or {}).get("taught_concepts"),
        "summary_blocks": summary_blocks,
    }


async def _fetch_documents(
    user_id: str, topic_id: str | None = None, limit: int = _MAX_DOCUMENT_CHUNKS
) -> list:
    """Fetch this topic's own documents first, then fill the rest of the
    budget with the user's user-wide ingested chunks. Empty list on failure."""
    try:
        topic_chunks: list = []
        if topic_id:
            topic_chunks = await embeddings_col().find(
                {"user_id": user_id, "metadata.source": "topic_document", "metadata.topic_id": topic_id},
                {"_id": 0, "text": 1, "metadata.filename": 1},
            ).to_list(length=limit)

        remaining = limit - len(topic_chunks)
        general_chunks: list = []
        if remaining > 0:
            cursor = embeddings_col().find(
                {"user_id": user_id, "metadata.source": "ingestion"},
                {"_id": 0, "text": 1, "metadata.filename": 1},
            ).limit(remaining)
            general_chunks = await cursor.to_list(length=remaining)

        return topic_chunks + general_chunks
    except Exception as e:
        logger.warning("Document fetch failed for user=%s: %s. Returning no documents.", user_id, e)
        return []


# ---------------------------------------------------------------------------
# Topic conversation window preparation (Req 9.1–9.5)
# ---------------------------------------------------------------------------


def _validate_thread_entry(entry: dict) -> bool:
    """Validate a thread entry (Message or SummaryBlock).

    Returns True if the entry is valid, False if it should be skipped.
    For SummaryBlocks, checks required fields: type, id, summary, compactedRange
    (with from/to), tokenCount.
    For Messages, checks: type, role, content, timestamp.
    """
    if not isinstance(entry, dict):
        return False

    entry_type = entry.get("type")

    if entry_type == "message":
        # Must have role, content, and timestamp
        role = entry.get("role")
        content = entry.get("content")
        timestamp = entry.get("timestamp")
        if role not in ("user", "assistant"):
            return False
        if not content or not isinstance(content, str):
            return False
        if timestamp is None:
            return False
        return True

    elif entry_type == "summary":
        # Must have id, summary, compactedRange.from, compactedRange.to, tokenCount
        if not entry.get("id"):
            return False
        if not entry.get("summary") or not isinstance(entry.get("summary"), str):
            return False
        compacted_range = entry.get("compactedRange")
        if not isinstance(compacted_range, dict):
            return False
        if compacted_range.get("from") is None or compacted_range.get("to") is None:
            return False
        token_count = entry.get("tokenCount")
        if token_count is None or not isinstance(token_count, (int, float)):
            return False
        if token_count < 0:
            return False
        return True

    else:
        # Unknown type
        return False


def _get_sort_timestamp(entry: dict) -> datetime:
    """Extract the chronological sort timestamp from a validated entry.

    Messages sort by their timestamp field.
    SummaryBlocks sort by their compactedRange.from field (Req 9.2).
    """
    entry_type = entry.get("type")
    if entry_type == "summary":
        ts = entry["compactedRange"]["from"]
    else:
        ts = entry["timestamp"]

    # Handle both datetime objects and ISO strings
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        # Try ISO format parsing
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.min
    return datetime.min


def _get_entry_token_count(entry: dict) -> int:
    """Get the token count for a validated entry.

    SummaryBlocks use their stored tokenCount (Req 9.4).
    Messages use their stored tokenCount or estimate from content.
    """
    # Use pre-computed tokenCount if available
    token_count = entry.get("tokenCount")
    if isinstance(token_count, (int, float)) and token_count >= 0:
        return int(token_count)

    # Fall back to content-based estimation for messages
    content = entry.get("content") or entry.get("summary") or ""
    return count_tokens(content)


def prepare_conversation_window(
    messages: list[dict],
    max_tokens: int | None = None,
) -> list[dict]:
    """Prepare a topic's messages (including SummaryBlocks) for the LLM conversation window.

    This function:
    1. Validates each entry — skips malformed SummaryBlocks with a warning log (Req 9.5)
    2. Ensures SummaryBlocks are positioned chronologically by their compactedRange.from
       timestamp (Req 9.2)
    3. Counts each SummaryBlock's tokenCount toward the window budget (Req 9.4)
    4. Returns the processed messages in chronological order for context assembly

    Args:
        messages: List of message dicts and SummaryBlock dicts from the topic's
                  messages array.
        max_tokens: Optional budget limit for the conversation window. If provided,
                    drops oldest entries to fit within budget.

    Returns:
        Processed list of message/summary entries ready for LLM context assembly.
    """
    if not messages:
        return []

    # Step 1: Validate entries, skip malformed ones with a warning
    valid_entries: list[dict] = []
    for entry in messages:
        if _validate_thread_entry(entry):
            valid_entries.append(entry)
        else:
            logger.warning(
                "Skipping malformed thread entry during context assembly: %s",
                _safe_entry_summary(entry),
            )

    if not valid_entries:
        return []

    # Step 2: Sort chronologically — SummaryBlocks by compactedRange.from (Req 9.2)
    valid_entries.sort(key=_get_sort_timestamp)

    # Step 3: Apply token budget if specified — drop oldest entries first
    if max_tokens is not None and max_tokens > 0:
        valid_entries = _apply_token_budget(valid_entries, max_tokens)

    return valid_entries


def _apply_token_budget(entries: list[dict], max_tokens: int) -> list[dict]:
    """Drop oldest entries until total tokens fit within max_tokens budget.

    Entries are assumed to be in chronological order. We remove from the front
    (oldest) until the remaining entries fit within the budget.
    """
    # Calculate total tokens
    total_tokens = sum(_get_entry_token_count(e) for e in entries)

    if total_tokens <= max_tokens:
        return entries

    # Drop from the front (oldest first) until we fit
    idx = 0
    while idx < len(entries) and total_tokens > max_tokens:
        total_tokens -= _get_entry_token_count(entries[idx])
        idx += 1

    return entries[idx:]


def _safe_entry_summary(entry: Any) -> str:
    """Create a safe log-friendly summary of a malformed entry."""
    if not isinstance(entry, dict):
        return f"non-dict entry: {type(entry).__name__}"
    entry_type = entry.get("type", "<missing>")
    entry_id = entry.get("id", "<missing>")
    return f"type={entry_type} id={entry_id}"
