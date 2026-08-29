"""CompactionService — monitors token usage and orchestrates compaction.

Handles message selection for compaction, LLM summarization orchestration,
summary block creation, and skill graph updates at compaction points.

Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 10.1, 10.2, 8.4, 8.5
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from app.config.database import compaction_events_col, topics_col
from app.config.settings import get_settings
from app.services.token_counter import TokenCounter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env-configurable with sensible defaults)
# ---------------------------------------------------------------------------

DEFAULT_COMPACTION_THRESHOLD = 60
"""Default compaction threshold as percentage of available capacity."""

DEFAULT_PREEMPTIVE_THRESHOLD = 40
"""Pre-emptive compaction threshold (on topic load) as percentage."""

MIN_THRESHOLD = 30
MAX_THRESHOLD = 90

MAX_CONSECUTIVE_FAILURES = 3
"""After this many consecutive LLM failures, notify user to start a new topic."""

MAX_SKILL_UPDATE_RETRIES = 3
"""Maximum retry attempts for skill graph updates."""

SKILL_CHECK_MESSAGE_WINDOW = 20
"""How many recent messages to feed the periodic (non-compaction) skill checkpoint."""

_LLM_TIMEOUT_SECONDS = 30
"""Timeout for the summarization LLM call."""

_SUMMARIZATION_MODEL = "claude-haiku-4-5-20251001"
"""Model used for compaction summarization (fast, cost-effective)."""

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_COMPACTION_PROMPT_FILE = "compaction_summarize.md"

# Tool schema for structured output from the summarization LLM call
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
                        "topic": {"type": "string"},
                        "new_level": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced", "expert"],
                        },
                        "gap": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weak_areas": {"type": "array", "items": {"type": "string"}},
                        "strong_areas": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["topic", "new_level", "gap", "weak_areas", "strong_areas"],
                },
                "description": "Skill updates detected from the conversation. Empty array if no progress detected.",
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
        },
        "required": ["summary", "skill_updates", "taught_concepts"],
    },
}

MAX_TAUGHT_CONCEPTS = 30
"""Cap on a topic's stored taughtConcepts list — oldest dropped past this,
same bounded-growth intent as the rolling summary itself."""

# Valid skill levels for validation
_VALID_LEVELS = {"beginner", "intermediate", "advanced", "expert"}


def _load_compaction_prompt() -> str:
    """Load the compaction summarization prompt template."""
    filepath = _PROMPTS_DIR / _COMPACTION_PROMPT_FILE
    if not filepath.exists():
        raise FileNotFoundError(f"Compaction prompt template not found: {filepath}")
    return filepath.read_text(encoding="utf-8")


def _format_conversation_excerpt(messages: list[dict]) -> str:
    """Format messages into a readable conversation excerpt for the prompt.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        A formatted string with each message on its own line.
    """
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _validate_skill_updates(skill_updates: list) -> list[dict]:
    """Validate and sanitize skill updates from LLM output.

    Filters out any updates that don't match the expected schema.
    Returns only valid updates.

    Args:
        skill_updates: Raw list of skill update dicts from LLM.

    Returns:
        List of validated skill update dicts.
    """
    validated = []
    for update in skill_updates:
        if not isinstance(update, dict):
            continue

        topic = update.get("topic")
        new_level = update.get("new_level")
        gap = update.get("gap")
        weak_areas = update.get("weak_areas")
        strong_areas = update.get("strong_areas")

        # Validate required fields
        if not isinstance(topic, str) or not topic.strip():
            continue
        if new_level not in _VALID_LEVELS:
            continue
        if not isinstance(gap, int) or gap < 0 or gap > 100:
            # Try to coerce numeric types
            try:
                gap = int(gap)
                if gap < 0 or gap > 100:
                    continue
            except (TypeError, ValueError):
                continue
        if not isinstance(weak_areas, list):
            weak_areas = []
        if not isinstance(strong_areas, list):
            strong_areas = []

        # Filter to only string items in areas
        weak_areas = [a for a in weak_areas if isinstance(a, str)]
        strong_areas = [a for a in strong_areas if isinstance(a, str)]

        validated.append({
            "topic": topic.strip(),
            "new_level": new_level,
            "gap": gap,
            "weak_areas": weak_areas,
            "strong_areas": strong_areas,
        })

    return validated


def _get_compaction_threshold() -> int:
    """Read compaction threshold from env or use default (60%)."""
    env_val = os.environ.get("COMPACTION_THRESHOLD")
    if env_val:
        try:
            parsed = int(env_val)
            if MIN_THRESHOLD <= parsed <= MAX_THRESHOLD:
                return parsed
        except ValueError:
            pass
    return DEFAULT_COMPACTION_THRESHOLD


def _get_preemptive_threshold() -> int:
    """Read pre-emptive threshold from env or use default (40%)."""
    env_val = os.environ.get("PREEMPTIVE_THRESHOLD")
    if env_val:
        try:
            parsed = int(env_val)
            if MIN_THRESHOLD <= parsed <= MAX_THRESHOLD:
                return parsed
        except ValueError:
            pass
    return DEFAULT_PREEMPTIVE_THRESHOLD


def _find_rolling_summary(messages: list[dict]) -> dict | list[dict] | None:
    """Locate the topic's summary entry/entries in its messages array.

    Returns:
        None if no summary entries exist.
        The single summary dict if exactly one exists (the steady-state case
        post-migration — see rolling-topic-summary spec Requirement 2.1).
        A list of summary dicts if more than one exists (legacy multi-block
        state from before rolling summaries — signals migration is needed).
    """
    summaries = [msg for msg in messages if msg.get("type") == "summary"]
    if not summaries:
        return None
    if len(summaries) == 1:
        return summaries[0]
    return summaries


class CompactionService:
    """Monitors token usage and orchestrates compaction."""

    def __init__(self, token_counter: TokenCounter | None = None):
        self._token_counter = token_counter or TokenCounter()
        self._compaction_in_progress: set[str] = set()
        self._compaction_threshold = _get_compaction_threshold()
        self._preemptive_threshold = _get_preemptive_threshold()
        self._consecutive_failures: dict[str, int] = {}  # topic_id → failure count

    def select_messages_to_compact(
        self, messages: list[dict], target_reclamation: int
    ) -> list[dict]:
        """Select messages for compaction from a topic's messages array.

        Selection rules (from requirements):
        1. Select the OLDEST non-summarized messages first (skip SummaryBlocks)
        2. Never split user-assistant message pairs — if including one, include both
        3. Select messages until the token total of selected messages meets or
           exceeds the target_reclamation amount
        4. If a pair would exceed target_reclamation, still include the full pair
        5. Skip compaction entirely (return empty list) if fewer than 2 complete
           user-assistant pairs are available for selection

        Args:
            messages: The full messages array (may include SummaryBlocks with type="summary")
            target_reclamation: Token count to reclaim (minimum)

        Returns:
            List of message dicts selected for compaction (in chronological order).
            Empty list if compaction should be skipped.
        """
        # Step 1: Filter out SummaryBlocks — only consider type="message" entries
        candidates = [
            msg for msg in messages
            if msg.get("type") != "summary"
        ]

        # Step 2: Group consecutive user→assistant pairs
        pairs = self._group_pairs(candidates)

        # Step 3: Skip compaction if fewer than 2 complete pairs available
        if len(pairs) < 2:
            return []

        # Step 4: Iterate pairs oldest-first, accumulating token counts
        selected_messages: list[dict] = []
        accumulated_tokens = 0

        for pair in pairs:
            pair_tokens = sum(
                msg.get("tokenCount", 0) or self._token_counter.count_message(msg)
                for msg in pair
            )
            selected_messages.extend(pair)
            accumulated_tokens += pair_tokens

            # Stop when accumulated tokens >= target_reclamation
            if accumulated_tokens >= target_reclamation:
                break

        return selected_messages

    def _group_pairs(self, candidates: list[dict]) -> list[list[dict]]:
        """Group consecutive user→assistant message pairs.

        A "pair" is a user message immediately followed by an assistant message.
        Orphaned messages (user without following assistant, or assistant without
        preceding user) are skipped to avoid splitting pairs.

        Args:
            candidates: List of message dicts (no SummaryBlocks), in chronological order.

        Returns:
            List of pairs, where each pair is a list of [user_msg, assistant_msg].
        """
        pairs: list[list[dict]] = []
        i = 0

        while i < len(candidates):
            msg = candidates[i]

            # Look for a user message followed by an assistant message
            if msg.get("role") == "user":
                if i + 1 < len(candidates) and candidates[i + 1].get("role") == "assistant":
                    pairs.append([candidates[i], candidates[i + 1]])
                    i += 2
                else:
                    # Orphaned user message (no following assistant) — skip
                    i += 1
            else:
                # Orphaned assistant message (no preceding user) — skip
                i += 1

        return pairs

    # ------------------------------------------------------------------
    # Compaction triggering (Req 6.1, 6.2, 6.3, 6.5)
    # ------------------------------------------------------------------

    async def should_compact(self, topic_id: str, user_id: str, on_load: bool = False) -> bool:
        """Check if compaction should be triggered for a topic.

        Args:
            topic_id: The topic to check.
            user_id: The owning user's ID.
            on_load: If True, uses the lower on-load threshold (40%).

        Returns:
            True if compaction should be triggered.

        Logic:
        - Guard against concurrent compaction: if already in progress, return False
        - Fetch topic's messages and calculate current token usage percent
        - If on_load=True: trigger if usage > pre-emptive threshold (40%)
        - If on_load=False: trigger if usage > compaction threshold (default 60%)
        """
        # Concurrent compaction guard (Req 6.5)
        if topic_id in self._compaction_in_progress:
            return False

        # Fetch topic messages
        topic = await topics_col().find_one(
            {"topicId": topic_id, "userId": user_id},
            {"_id": 0, "messages": 1},
        )
        if not topic:
            return False

        messages = topic.get("messages", [])
        if not messages:
            return False

        usage_percent = self._token_counter.get_usage_percent(messages)

        threshold = self._preemptive_threshold if on_load else self._compaction_threshold
        return usage_percent > threshold

    # ------------------------------------------------------------------
    # LLM summarization stub (mockable for testing)
    # ------------------------------------------------------------------

    async def _call_summarization_llm(self, messages: list[dict]) -> dict:
        """Call Claude to summarize compacted messages and extract skill updates.

        The LLM is given the conversation excerpt and asked to produce:
        1. A narrative summary (3-5 sentences) capturing the key learning points
        2. Zero or more structured skill updates (topic, new_level, gap, weak_areas, strong_areas)

        Uses Anthropic's tool_use feature to get reliable JSON output.

        Args:
            messages: List of message dicts to summarize.

        Returns:
            Dict with:
            - "summary": str — the narrative summary
            - "skill_updates": list[dict] | None — skill updates or None if none detected
        """
        # Step 1: Format conversation excerpt
        conversation_excerpt = _format_conversation_excerpt(messages)

        # Step 2: Load and interpolate the prompt template
        prompt_template = _load_compaction_prompt()
        prompt_text = prompt_template.replace("{{conversation}}", conversation_excerpt)

        # Step 3: Call Claude with tool_use for structured output
        settings = get_settings()
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model=_SUMMARIZATION_MODEL,
                    max_tokens=1024,
                    tools=[_COMPACTION_TOOL_SCHEMA],
                    tool_choice={"type": "tool", "name": "compaction_result"},
                    messages=[
                        {
                            "role": "user",
                            "content": prompt_text,
                        }
                    ],
                ),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("Compaction summarization LLM call timed out after %ds", _LLM_TIMEOUT_SECONDS)
            raise
        except Exception as e:
            logger.error("Compaction summarization LLM call failed: %s", str(e))
            raise

        # Step 4: Parse the tool_use response
        return self._parse_tool_use_response(response)

    async def _call_merge_summarization_llm(
        self, existing_summary: dict | None, selected_messages: list[dict]
    ) -> dict:
        """Summarize newly-selected messages, folding in an existing rolling summary if present.

        When `existing_summary` is None, this is identical to `_call_summarization_llm`.
        When present, the prior summary text is prepended as a synthetic "PRIOR SUMMARY"
        turn so the same prompt template (which instructs the LLM to fold prior + new
        into ONE updated summary) and the same tool schema/parsing path are reused as-is.
        """
        if existing_summary is None:
            return await self._call_summarization_llm(selected_messages)

        prior_entry = {"role": "PRIOR SUMMARY", "content": existing_summary["summary"]}
        return await self._call_summarization_llm([prior_entry] + selected_messages)

    def _parse_tool_use_response(self, response) -> dict:
        """Parse the Anthropic tool_use response to extract summary and skill updates.

        Args:
            response: The Anthropic API response object.

        Returns:
            Dict with "summary" and "skill_updates" keys.

        Raises:
            ValueError: If the response doesn't contain a valid tool_use block.
        """
        # Find the tool_use content block
        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "compaction_result":
                tool_input = block.input
                break

        if tool_input is None:
            logger.error("LLM response did not contain expected tool_use block")
            raise ValueError("LLM response missing compaction_result tool call")

        # Extract and validate summary
        summary = tool_input.get("summary", "")
        if not isinstance(summary, str) or not summary.strip():
            logger.error("LLM returned empty or invalid summary")
            raise ValueError("LLM returned empty summary")

        # Extract and validate skill updates
        raw_skill_updates = tool_input.get("skill_updates", [])
        if not isinstance(raw_skill_updates, list):
            raw_skill_updates = []

        # Validate each skill update
        validated_updates = _validate_skill_updates(raw_skill_updates)

        raw_taught_concepts = tool_input.get("taught_concepts", [])
        if not isinstance(raw_taught_concepts, list):
            raw_taught_concepts = []
        taught_concepts = [c.strip() for c in raw_taught_concepts if isinstance(c, str) and c.strip()]

        return {
            "summary": summary.strip(),
            "skill_updates": validated_updates if validated_updates else None,
            "taught_concepts": taught_concepts,
        }

    # ------------------------------------------------------------------
    # Compaction orchestration (Req 7.3, 7.4, 7.5, 7.6, 10.3)
    # ------------------------------------------------------------------

    async def extract_skill_updates_only(self, topic_id: str, user_id: str) -> None:
        """Periodic skill-graph checkpoint, independent of the compaction token threshold.

        Compaction only extracts skill updates as a side effect of reclaiming context
        space, so a topic that never grows big enough to compact never updates the
        skill graph. This runs the same summarization LLM call on the most recent
        messages and applies any skill updates, without touching the topic's messages
        (no summary block, no version bump) — the topic itself is unaffected.

        Best-effort: any failure is logged and swallowed, same as compaction's own
        skill-update path.
        """
        topic = await topics_col().find_one({"topicId": topic_id, "userId": user_id}, {"_id": 0})
        if not topic:
            return
        recent = [m for m in topic.get("messages", []) if m.get("type") == "message"][
            -SKILL_CHECK_MESSAGE_WINDOW:
        ]
        if not recent:
            return

        try:
            llm_result = await self._call_summarization_llm(recent)
        except Exception as e:
            logger.error("Skill checkpoint LLM call failed for topic %s: %s", topic_id, str(e))
            return

        skill_updates = llm_result.get("skill_updates")
        if skill_updates:
            await self._apply_skill_updates(user_id, skill_updates)

        taught_concepts = llm_result.get("taught_concepts")
        if taught_concepts:
            await self._apply_taught_concepts(topic_id, user_id, taught_concepts)

    async def _apply_taught_concepts(self, topic_id: str, user_id: str, new_concepts: list[str]) -> None:
        """Append newly-taught concepts onto the topic's `taughtConcepts` list —
        an L3 (episodic memory) record, concept-grained instead of narrative-
        grained (TS-1: episodic memory should say what was previously taught
        in a topic, not just a vague session narrative). Deduplicated, capped at MAX_TAUGHT_CONCEPTS
        (oldest dropped first). Best-effort: a failure here never blocks the
        summary/skill-update write it rides alongside.
        """
        try:
            topic = await topics_col().find_one(
                {"topicId": topic_id, "userId": user_id}, {"_id": 0, "taughtConcepts": 1},
            )
            if topic is None:
                return
            existing = topic.get("taughtConcepts") or []
            merged = existing + [c for c in new_concepts if c not in existing]
            merged = merged[-MAX_TAUGHT_CONCEPTS:]
            await topics_col().update_one(
                {"topicId": topic_id, "userId": user_id},
                {"$set": {"taughtConcepts": merged}},
            )
        except Exception as e:
            logger.warning(
                "Failed to persist taught_concepts for topic=%s user=%s: %s", topic_id, user_id, e,
            )

    async def compact(self, topic_id: str, user_id: str) -> dict | None:
        """Execute compaction for a topic.

        Orchestration flow:
        1. Guard against concurrent compaction (skip if already in progress)
        2. Fetch topic document
        3. Calculate target reclamation (bring usage below threshold)
        4. Select messages to compact via select_messages_to_compact()
        5. Call LLM with summarization prompt to produce narrative summary
        6. Parse LLM response for skill graph updates
        7. Create SummaryBlock
        8. Replace compacted messages with SummaryBlock in the topic (atomic)
        9. CRITICAL: Messages are only removed AFTER SummaryBlock is persisted
        10. Update skill graph if updates were extracted
        11. Log CompactionEvent

        Error handling (Req 10.1, 10.2):
        - On LLM failure: preserves all messages, increments failure counter, logs error
        - After 3 consecutive failures: user notification available via get_user_notification()
        - On success: resets consecutive failure counter to 0

        Returns:
            CompactionResult dict or None if compaction was skipped/failed.
        """
        # Concurrent compaction guard (Req 6.5)
        if topic_id in self._compaction_in_progress:
            return None

        self._compaction_in_progress.add(topic_id)
        try:
            result = await self._execute_compaction(topic_id, user_id)
            # On success, reset consecutive failure counter
            if result is not None:
                self._consecutive_failures[topic_id] = 0
            return result
        except Exception as e:
            # LLM failure or other error — preserve messages, increment failure counter
            failures = self._consecutive_failures.get(topic_id, 0) + 1
            self._consecutive_failures[topic_id] = failures
            logger.error(
                "Compaction failed for topic %s (attempt %d): %s",
                topic_id,
                failures,
                str(e),
            )
            if failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "Topic %s has failed compaction %d consecutive times — "
                    "user should be notified to consider starting a new topic",
                    topic_id,
                    failures,
                )
            return None
        finally:
            self._compaction_in_progress.discard(topic_id)

    def get_user_notification(self, topic_id: str) -> dict | None:
        """Return notification info if 3 consecutive compaction failures occurred.

        After 3 consecutive failures, the user should be notified that the thread
        is getting long and they should consider starting a new topic (Req 10.2).

        Returns:
            Dict with notification details or None if no notification needed.
        """
        failures = self._consecutive_failures.get(topic_id, 0)
        if failures >= MAX_CONSECUTIVE_FAILURES:
            return {
                "type": "compaction_failure",
                "message": (
                    "Your conversation thread is getting long. "
                    "Consider starting a new topic for continued learning."
                ),
                "consecutive_failures": failures,
            }
        return None

    async def _migrate_legacy_summaries(self, topic_id: str, user_id: str, topic: dict) -> dict | None:
        """Collapse a topic's multiple legacy SummaryBlocks into one RollingSummary.

        Runs lazily — only invoked from _execute_compaction when more than one
        summary entry is found (state from before rolling summaries shipped).
        Merges all existing summaries oldest-to-newest via one summarization LLM
        call. On failure, leaves the topic's SummaryBlocks untouched and returns
        None so the caller skips this turn's compaction (retried next threshold
        crossing, same as any other compaction failure).
        """
        messages = topic.get("messages", [])
        current_version = topic.get("version", 0)
        legacy = [m for m in messages if m.get("type") == "summary"]
        if len(legacy) < 2:
            return legacy[0] if legacy else None

        legacy.sort(key=lambda s: s.get("compactedRange", {}).get("from") or s.get("createdAt"))

        # Reuse the merge prompt path: each legacy summary becomes a "PRIOR SUMMARY"
        # turn, oldest first, so the LLM folds them into one narrative.
        synthetic = [{"role": "PRIOR SUMMARY", "content": s["summary"]} for s in legacy]
        try:
            llm_result = await self._call_summarization_llm(synthetic)
        except Exception as e:
            logger.error("Legacy summary migration failed for topic %s: %s", topic_id, str(e))
            return None

        merged_ids: list[str] = []
        for s in legacy:
            for mid in s.get("compactedMessageIds", []):
                if mid not in merged_ids:
                    merged_ids.append(mid)

        now = datetime.now(timezone.utc)
        merged_summary_text = llm_result["summary"]
        merged_block = {
            "type": "summary",
            "id": legacy[0]["id"],
            "summary": merged_summary_text,
            "compactedMessageIds": merged_ids,
            "compactedRange": {
                "from": legacy[0]["compactedRange"]["from"],
                "to": legacy[-1]["compactedRange"]["to"],
            },
            "messageCount": sum(s.get("messageCount", 0) for s in legacy),
            "tokenCount": self._token_counter.count_message({"content": merged_summary_text}),
            "createdAt": legacy[0].get("createdAt", now),
            "updatedAt": now,
            "compactionEventId": legacy[-1].get("compactionEventId", ""),
        }

        legacy_ids = {s["id"] for s in legacy}
        new_messages = []
        inserted = False
        for msg in messages:
            if msg.get("type") == "summary" and msg.get("id") in legacy_ids:
                if not inserted:
                    new_messages.append(merged_block)
                    inserted = True
            else:
                new_messages.append(msg)

        new_token_estimate = self._token_counter.count_window(new_messages)
        result = await topics_col().update_one(
            {"topicId": topic_id, "userId": user_id, "version": current_version},
            {
                "$set": {
                    "messages": new_messages,
                    "metadata.currentTokenEstimate": new_token_estimate,
                    "version": current_version + 1,
                },
            },
        )
        if result.modified_count != 1:
            logger.error(
                "Legacy summary migration failed: concurrent write conflict for topic %s", topic_id
            )
            return None

        logger.info(
            "Migrated %d legacy SummaryBlocks into one rolling summary for topic %s",
            len(legacy),
            topic_id,
        )
        return merged_block

    async def _execute_compaction(self, topic_id: str, user_id: str) -> dict | None:
        """Internal compaction execution logic."""
        # Step 1: Fetch topic document
        topic = await topics_col().find_one(
            {"topicId": topic_id, "userId": user_id},
        )
        if not topic:
            logger.warning("Compaction skipped: topic %s not found", topic_id)
            return None

        messages = topic.get("messages", [])

        # Step 1b: Collapse legacy multi-block state before doing anything else.
        # If migration is needed and fails, skip this turn's compaction entirely —
        # it will retry on the next threshold crossing (Req 2.2, 2.3).
        rolling = _find_rolling_summary(messages)
        if isinstance(rolling, list):
            migrated = await self._migrate_legacy_summaries(topic_id, user_id, topic)
            if migrated is None:
                logger.warning(
                    "Compaction skipped: legacy summary migration failed for topic %s", topic_id
                )
                return None
            topic = await topics_col().find_one({"topicId": topic_id, "userId": user_id})
            messages = topic.get("messages", [])
            rolling = _find_rolling_summary(messages)

        existing_summary = rolling  # dict or None — never a list past this point
        current_version = topic.get("version", 0)

        # Step 2: Calculate target reclamation
        capacity = self._token_counter.get_capacity()
        current_tokens = self._token_counter.count_window(messages)
        target_usage = int(capacity * (self._compaction_threshold / 100))
        target_reclamation = max(0, current_tokens - target_usage)

        if target_reclamation <= 0:
            logger.info("Compaction skipped: no reclamation needed for topic %s", topic_id)
            return None

        # Step 3: Select messages to compact
        selected = self.select_messages_to_compact(messages, target_reclamation)
        if not selected:
            logger.info("Compaction skipped: insufficient messages for topic %s", topic_id)
            return None

        # Step 4: Call LLM for summarization, folding in the existing rolling
        # summary (if any) instead of producing an independent new block.
        llm_result = await self._call_merge_summarization_llm(existing_summary, selected)
        summary_text = llm_result["summary"]
        skill_updates = llm_result.get("skill_updates")
        taught_concepts = llm_result.get("taught_concepts")

        # Step 5: Build the replacement RollingSummary — reuse the existing
        # block's id/from-timestamp when merging, so this is a replace-in-place,
        # not an append (Req 1.3, 1.4, 1.5, 1.6).
        summary_token_count = self._token_counter.count_message({"content": summary_text})
        new_ids = [msg["id"] for msg in selected]
        now = datetime.now(timezone.utc)
        event_id = str(uuid.uuid4())

        if existing_summary:
            compacted_message_ids = list(existing_summary.get("compactedMessageIds", []))
            for mid in new_ids:
                if mid not in compacted_message_ids:
                    compacted_message_ids.append(mid)
            compacted_range_from = existing_summary["compactedRange"]["from"]
            summary_block_id = existing_summary["id"]
            message_count = existing_summary.get("messageCount", 0) + len(selected)
            created_at = existing_summary.get("createdAt", now)
        else:
            compacted_message_ids = new_ids
            compacted_range_from = selected[0].get("timestamp")
            summary_block_id = str(uuid.uuid4())
            message_count = len(selected)
            created_at = now

        summary_block = {
            "type": "summary",
            "id": summary_block_id,
            "summary": summary_text,
            "compactedMessageIds": compacted_message_ids,
            "compactedRange": {
                "from": compacted_range_from,
                "to": selected[-1].get("timestamp"),
            },
            "messageCount": message_count,
            "tokenCount": summary_token_count,
            "createdAt": created_at,
            "updatedAt": now,
            "compactionEventId": event_id,
        }

        # Step 6: Replace compacted messages AND the prior RollingSummary (if any)
        # with the single merged block (atomic operation).
        # CRITICAL: Messages are only removed AFTER the block is persisted (Req 10.3)
        new_ids_set = set(new_ids)
        new_messages = []
        summary_inserted = False

        for msg in messages:
            msg_id = msg.get("id")
            is_prior_summary = (
                existing_summary is not None
                and msg.get("type") == "summary"
                and msg_id == existing_summary["id"]
            )
            if msg_id in new_ids_set or is_prior_summary:
                # Insert the merged block at the position of the first item removed
                if not summary_inserted:
                    new_messages.append(summary_block)
                    summary_inserted = True
                # Skip this compacted/superseded entry
            else:
                new_messages.append(msg)

        # Calculate new token estimate
        new_token_estimate = self._token_counter.count_window(new_messages)
        tokens_reclaimed = current_tokens - new_token_estimate

        # Step 7: Persist with optimistic concurrency
        result = await topics_col().update_one(
            {"topicId": topic_id, "userId": user_id, "version": current_version},
            {
                "$set": {
                    "messages": new_messages,
                    "metadata.currentTokenEstimate": new_token_estimate,
                    "version": current_version + 1,
                },
                "$inc": {"compactionCount": 1},
            },
        )

        if result.modified_count != 1:
            logger.error(
                "Compaction failed: concurrent write conflict for topic %s", topic_id
            )
            return None

        # Step 8: Log CompactionEvent (Req 7.6)
        compaction_event = {
            "eventId": event_id,
            "topicId": topic_id,
            "userId": user_id,
            "timestamp": now,
            "messagesCompacted": len(selected),
            "tokensBeforeCompaction": current_tokens,
            "tokensAfterCompaction": new_token_estimate,
            "tokensReclaimed": tokens_reclaimed,
            "skillUpdateGenerated": skill_updates is not None and len(skill_updates) > 0,
            "skillUpdate": skill_updates,
            "summaryBlockId": summary_block_id,
        }
        await compaction_events_col().insert_one(compaction_event)

        # Step 9: Update skill graph if updates were extracted (Req 8.1, 8.2).
        # Extraction is scoped to `selected` (the newly-compacted messages) only —
        # never the merged summary text — so progress already applied by prior
        # compactions is never re-derived (Req 5.1, 5.2).
        if skill_updates:
            await self._apply_skill_updates(user_id, skill_updates)

        if taught_concepts:
            await self._apply_taught_concepts(topic_id, user_id, taught_concepts)

        logger.info(
            "Compaction completed — topic=%s, messages_compacted=%d, tokens_reclaimed=%d",
            topic_id,
            len(selected),
            tokens_reclaimed,
        )

        return {
            "summaryBlock": summary_block,
            "skillUpdate": skill_updates,
            "messagesCompacted": len(selected),
            "tokensReclaimed": tokens_reclaimed,
        }

    async def _apply_skill_updates(self, user_id: str, skill_updates: list[dict]) -> None:
        """Apply extracted skill updates to the skill graph with retry logic.

        Retries up to MAX_SKILL_UPDATE_RETRIES (3) times on failure.
        On permanent failure, logs the error for operator review but does not
        raise — the summary block is preserved regardless (Req 8.4, 8.5).

        Args:
            user_id: The user's ID.
            skill_updates: List of skill update dicts from LLM response.
        """
        from app.models.session import SessionSkillUpdate
        from app.services.skill_graph_repo import apply_update

        for attempt in range(MAX_SKILL_UPDATE_RETRIES):
            try:
                for update_data in skill_updates:
                    skill_update = SessionSkillUpdate(**update_data)
                    await apply_update(user_id, skill_update)
                return  # success
            except Exception as e:
                logger.error(
                    "Skill update attempt %d failed for user %s: %s",
                    attempt + 1,
                    user_id,
                    str(e),
                )
                if attempt == MAX_SKILL_UPDATE_RETRIES - 1:
                    logger.error(
                        "Skill update permanently failed after %d attempts for user %s — "
                        "discarding. Summary block preserved. (Req 8.5)",
                        MAX_SKILL_UPDATE_RETRIES,
                        user_id,
                    )
