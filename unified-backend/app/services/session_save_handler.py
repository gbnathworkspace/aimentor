"""SessionSaveHandler: orchestrates end-of-session processing.

Performs a combined LLM call to produce a narrative summary and skill update
in a single request. Handles retry logic, JSON parsing with regex fallback,
Pydantic validation of skill updates, and fallback summary generation.

Pipeline:
1. Read transcript from session document
2. Call LLM with combined prompt (summary + skill_update)
3. Parse and validate response
4. Persist summary to session doc
5. Upsert skill graph (non-blocking on failure)
6. Fire async embedding task
7. Transition status to 'ended'
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import anthropic

from app.config.database import sessions_col, skill_graph_col
from app.config.settings import get_settings
from app.models.session import (
    Message,
    SessionEndResult,
    SessionSkillUpdate,
    SessionStatus,
)
from app.services.message_store import MessageStore
from app.services.profiling_agent import propose_changes as propose_profile_changes
from app.services.session_manager import SessionManager
from app.services.skill_graph_repo import apply_update as _apply_skill_graph_update

logger = logging.getLogger(__name__)

# Max transcript length sent to the LLM (most recent chars)
_MAX_TRANSCRIPT_CHARS = 40_000

# LLM constraints
_MAX_OUTPUT_TOKENS = 500
_TIMEOUT_SECONDS = 30
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2

# Fallback summary constraints
_FALLBACK_MAX_CHARS = 300
_FALLBACK_PREFIX = "Session covered: "
_SHORT_SESSION_FALLBACK = "Session ended before meaningful interaction occurred."

# Regex pattern to extract narrative_summary from malformed JSON
_NARRATIVE_REGEX = re.compile(
    r'"narrative_summary"\s*:\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)


def _build_combined_prompt(
    transcript: str, topic: str, mode: str, current_level: str = "beginner"
) -> str:
    """Build the LLM prompt requesting both narrative_summary and skill_update.

    Anchors grading to the student's current level with an explicit rubric so
    `new_level` reflects demonstrated mastery rather than an unguided guess, and
    can move at most one level per session (no wild swings).
    """
    return (
        f"You are analyzing a completed learning session.\n"
        f"Session topic: {topic}\n"
        f"Session mode: {mode}\n"
        f"Student's current level: {current_level}\n\n"
        f"Grade against this rubric (order: beginner < intermediate < advanced < expert):\n"
        f"  - beginner: recalls basics only with prompting\n"
        f"  - intermediate: applies concepts independently on standard problems\n"
        f"  - advanced: handles edge cases and explains trade-offs\n"
        f"  - expert: generalizes and could teach the topic\n"
        f"Rules: pick new_level from the transcript evidence only. Move at most ONE "
        f"level from the current level, and only when the next level's bar is clearly "
        f"met. If evidence is weak or mixed, keep the current level.\n\n"
        f"Based on the following transcript, produce a JSON object with exactly two keys:\n\n"
        f'1. "narrative_summary": A string of 3-5 sentences describing what was studied, '
        f"what the student was strong at, and what they were weak at. "
        f"Write it for future semantic search retrieval.\n\n"
        f'2. "skill_update": An object with the following fields:\n'
        f'   - "topic" (string): The main topic studied\n'
        f'   - "new_level" (string): One of "beginner", "intermediate", "advanced", "expert"\n'
        f'   - "gap" (integer): A score from 0 to 100 representing the knowledge gap\n'
        f'   - "weak_areas" (array of strings, max 10): Areas where the student struggled\n'
        f'   - "strong_areas" (array of strings, max 10): Areas where the student excelled\n'
        f'   - "eval_score" (string, optional): An evaluation score if applicable\n\n'
        f'3. "profile_signals" (array, can be empty): Clear signals about how this '
        f"student learns best or what motivates them, grounded in this transcript. "
        f"Only include a signal with real, specific evidence — return an empty array "
        f"if nothing stands out. Do NOT force a signal every session. Each item is one of:\n"
        f'   - {{"field": "style_note", "proposed_value": {{"category": '
        f'"pacing|communication|motivation|misconception|context", "note": "short '
        f'claim, under 140 chars"}}, "reason": "quote or paraphrase from the transcript"}}\n\n'
        f"Respond ONLY with the JSON object. No markdown, no code fences, no extra text.\n\n"
        f"<transcript>\n{transcript}\n</transcript>"
    )


def _truncate_transcript(messages: list[Message]) -> str:
    """Build transcript string from messages, truncating to most recent 40,000 chars."""
    transcript = "\n".join(
        f"{m.role.upper()}: {m.content}" for m in messages
    )
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript = transcript[-_MAX_TRANSCRIPT_CHARS:]
    return transcript


def _generate_fallback_summary(messages: list[Message]) -> str:
    """Generate a fallback summary from user messages when LLM fails.

    For sessions with <2 messages: returns short session fallback.
    Otherwise: combines first + last user message content, truncates to 300 chars,
    prefixed with "Session covered: ".
    """
    if len(messages) < 2:
        return _SHORT_SESSION_FALLBACK

    user_messages = [m for m in messages if m.role == "user"]

    if len(user_messages) < 1:
        return _SHORT_SESSION_FALLBACK

    first_content = user_messages[0].content if user_messages else ""
    last_content = user_messages[-1].content if len(user_messages) > 1 else first_content

    combined = f"{first_content} {last_content}"
    max_content_len = _FALLBACK_MAX_CHARS - len(_FALLBACK_PREFIX)
    if len(combined) > max_content_len:
        combined = combined[:max_content_len]

    return f"{_FALLBACK_PREFIX}{combined}"


def _parse_llm_response(raw_text: str) -> tuple[str | None, dict | None, list]:
    """Parse LLM response as JSON, with regex fallback for narrative_summary.

    Returns:
        Tuple of (narrative_summary, skill_update_dict, profile_signals).
        narrative_summary/skill_update_dict may be None; profile_signals
        defaults to [] if parsing/extraction fails (it's a best-effort extra,
        never required for a successful session-end).
    """
    narrative_summary = None
    skill_update_dict = None
    profile_signals: list = []

    # Attempt full JSON parse
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            narrative_summary = data.get("narrative_summary")
            if narrative_summary and not isinstance(narrative_summary, str):
                narrative_summary = None
            skill_update_dict = data.get("skill_update")
            if skill_update_dict and not isinstance(skill_update_dict, dict):
                skill_update_dict = None
            signals = data.get("profile_signals")
            if isinstance(signals, list):
                profile_signals = signals
            return narrative_summary, skill_update_dict, profile_signals
    except (json.JSONDecodeError, TypeError):
        logger.warning("LLM response is not valid JSON, attempting regex extraction")

    # Regex fallback for narrative_summary (skill_update/profile_signals are
    # skipped on malformed JSON — narrative_summary alone is worth recovering)
    match = _NARRATIVE_REGEX.search(raw_text)
    if match:
        # Unescape JSON string escapes
        raw_value = match.group(1)
        try:
            narrative_summary = json.loads(f'"{raw_value}"')
        except (json.JSONDecodeError, TypeError):
            narrative_summary = raw_value

    return narrative_summary, skill_update_dict, profile_signals


def _validate_skill_update(skill_update_dict: dict | None) -> SessionSkillUpdate | None:
    """Validate skill_update dict against the Pydantic SessionSkillUpdate model.

    Returns:
        Validated SessionSkillUpdate or None if validation fails.
    """
    if not skill_update_dict or not isinstance(skill_update_dict, dict):
        return None

    try:
        return SessionSkillUpdate(**skill_update_dict)
    except Exception as e:
        logger.warning("Skill update validation failed: %s", str(e))
        return None


async def _call_llm(prompt: str) -> str | None:
    """Make a single LLM call with timeout. Returns raw text or None on failure."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=_MAX_OUTPUT_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            ),
            timeout=_TIMEOUT_SECONDS,
        )

        # Extract text from response content blocks
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        return "".join(text_parts) if text_parts else None

    except asyncio.TimeoutError:
        logger.warning("LLM call timed out after %d seconds", _TIMEOUT_SECONDS)
        return None
    except Exception as e:
        logger.warning("LLM call failed: %s", str(e))
        return None


async def apply_skill_update(user_id: str, skill_update: SessionSkillUpdate) -> None:
    """Upsert skill graph node with the validated skill update.

    Delegates to skill_graph_repo.apply_update which handles the MongoDB
    upsert. Errors are logged internally — this function never raises.
    """
    await _apply_skill_graph_update(user_id, skill_update)


async def embed_summary(
    summary: str,
    user_id: str,
    session_id: str,
    topic: str,
    mode: str,
    ended_at: str | None = None,
) -> None:
    """Generate embedding and store in vector DB via EmbeddingService.

    Delegates to embedding_service.embed_and_store which handles:
    - Precondition checks (summary length, metadata completeness)
    - Voyage AI embedding generation
    - Atlas Vector Search upsert with metadata
    - Retry logic (3 attempts, exponential backoff)
    - Delayed retry on total failure (5 min)

    This function never raises — all errors are handled internally.
    """
    from app.services.embedding_service import embed_and_store

    try:
        await embed_and_store(
            summary=summary,
            user_id=user_id,
            session_id=session_id,
            topic=topic,
            mode=mode,
            ended_at=ended_at or "",
        )
    except Exception as e:
        logger.error(
            "Unexpected error in embed_summary for session_id=%s: %s",
            session_id,
            str(e),
        )


class SessionSaveHandler:
    """Orchestrates end-of-session processing: LLM call, parsing, persistence."""

    def __init__(self):
        self._message_store = MessageStore()
        self._session_manager = SessionManager()

    async def process_end(
        self, session_id: str, user_id: str, topic: str, mode: str
    ) -> SessionEndResult:
        """Full end-of-session pipeline.

        1. Read transcript from the session document
        2. Call LLM with combined prompt (summary + skill_update)
        3. Parse and validate response
        4. Persist summary to session doc
        5. Upsert skill graph (non-blocking on failure)
        6. Fire async embedding task
        7. Transition status to 'ended'

        Args:
            session_id: The session being ended.
            user_id: The owning user's ID.
            topic: Session topic for contextual prompting.
            mode: Session mode (topic, planning, doubt, evaluation).

        Returns:
            SessionEndResult with summary and optional skill_update.
        """
        # Step 1: Read transcript
        messages = await self._message_store.get_messages(session_id)

        # Short session handling
        if len(messages) < 2:
            summary = _SHORT_SESSION_FALLBACK
            await self._persist_summary(session_id, summary, skill_update=None)
            await self._transition_to_ended(session_id, user_id)
            # Fire async embedding for fallback summary too (requirement 6.5)
            ended_at = datetime.now(timezone.utc).isoformat()
            asyncio.create_task(
                embed_summary(summary, user_id, session_id, topic or "", mode, ended_at)
            )
            title = await self._get_session_title(session_id)
            return SessionEndResult(
                session_id=session_id,
                title=title,
                summary=summary,
                skill_update=None,
            )

        # Step 2: Build prompt and call LLM with retries.
        # Anchor grading to the student's current level (default beginner for a
        # brand-new topic) so new_level is rubric-graded, not an unguided guess.
        transcript = _truncate_transcript(messages)
        existing = await skill_graph_col().find_one(
            {"user_id": user_id, "topic": topic}, {"current_level": 1, "_id": 0}
        )
        current_level = (existing or {}).get("current_level", "beginner")
        prompt = _build_combined_prompt(transcript, topic, mode, current_level)

        raw_response = await self._call_llm_with_retries(prompt)

        # Step 3: Parse and validate
        narrative_summary = None
        validated_skill_update = None
        profile_signals: list = []

        if raw_response:
            narrative_summary, skill_update_dict, profile_signals = _parse_llm_response(raw_response)
            validated_skill_update = _validate_skill_update(skill_update_dict)

        # Determine final summary
        if narrative_summary:
            summary = narrative_summary
        else:
            summary = _generate_fallback_summary(messages)

        # Step 4: Persist summary
        await self._persist_summary(session_id, summary, validated_skill_update)

        # Step 5: Skill graph upsert (non-blocking on failure)
        if validated_skill_update:
            try:
                await apply_skill_update(user_id, validated_skill_update)
            except Exception as e:
                logger.warning(
                    "Skill graph update failed for session %s: %s",
                    session_id,
                    str(e),
                )

        # Step 5b: Propose L1 profile changes (non-blocking on failure — the
        # profiling agent never raises, but guard here too for defense-in-depth)
        if profile_signals:
            try:
                await propose_profile_changes(user_id, session_id, profile_signals)
            except Exception as e:
                logger.warning(
                    "Profile signal proposal failed for session %s: %s", session_id, str(e)
                )

        # Step 6: Transition to ended (before embedding so ended_at is available)
        await self._transition_to_ended(session_id, user_id)

        # Step 7: Fire async embedding (fire-and-forget)
        ended_at = datetime.now(timezone.utc).isoformat()
        asyncio.create_task(
            embed_summary(summary, user_id, session_id, topic, mode, ended_at)
        )

        title = await self._get_session_title(session_id)

        # Level change for the "you leveled up" tag (issue #16). current_level was
        # read before the update (Step 2); new_level is this session's grade.
        level_from = current_level if validated_skill_update else None
        level_to = (
            validated_skill_update.new_level.value if validated_skill_update else None
        )

        return SessionEndResult(
            session_id=session_id,
            title=title,
            summary=summary,
            skill_update=validated_skill_update,
            level_from=level_from,
            level_to=level_to,
        )

    async def _call_llm_with_retries(self, prompt: str) -> str | None:
        """Call LLM with retry logic: 3 total attempts, 2-second delay between."""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            result = await _call_llm(prompt)
            if result:
                return result

            if attempt < _MAX_ATTEMPTS:
                logger.info(
                    "LLM attempt %d/%d failed, retrying in %ds...",
                    attempt,
                    _MAX_ATTEMPTS,
                    _RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS)

        logger.error("All %d LLM attempts failed", _MAX_ATTEMPTS)
        return None

    async def _persist_summary(
        self,
        session_id: str,
        summary: str,
        skill_update: SessionSkillUpdate | None,
    ) -> None:
        """Persist the summary (and optional skill_update) to the session document."""
        now = datetime.now(timezone.utc).isoformat()
        update_fields: dict = {
            "summary": summary,
            "updated_at": now,
        }
        if skill_update:
            update_fields["skill_update"] = skill_update.model_dump(by_alias=False)

        await sessions_col().update_one(
            {"session_id": session_id},
            {"$set": update_fields},
        )

    async def _transition_to_ended(self, session_id: str, user_id: str) -> None:
        """Transition session status to ended."""
        try:
            await self._session_manager.transition_status(
                session_id, user_id, SessionStatus.ended
            )
        except Exception as e:
            logger.error(
                "Failed to transition session %s to ended: %s",
                session_id,
                str(e),
            )
            # Force-set status to ended as a last resort
            now = datetime.now(timezone.utc).isoformat()
            await sessions_col().update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "status": SessionStatus.ended.value,
                        "ended_at": now,
                        "updated_at": now,
                        "failure_reason": f"Transition error: {str(e)}",
                    }
                },
            )

    async def _get_session_title(self, session_id: str) -> str:
        """Retrieve the session title from the database."""
        session = await sessions_col().find_one(
            {"session_id": session_id}, {"title": 1}
        )
        if session and session.get("title"):
            return session["title"]
        return "Untitled session"
