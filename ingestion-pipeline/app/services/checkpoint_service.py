"""CheckpointService: two-phase checkpoint mechanism for session data preservation.

Phase 1 (auto_checkpoint): fire-and-forget transcript persistence every 5 turns.
Phase 2 (end_session): LLM summarization → SessionEndProcessor routing.
Recovery: orphaned session recovery on next session start.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.config.database import get_sessions_collection
from app.config.settings import get_settings
from app.services.session_end_processor import SessionEndProcessor

logger = logging.getLogger(__name__)


class CheckpointService:
    """Two-phase checkpoint mechanism for session data preservation."""

    CHECKPOINT_INTERVAL = 5  # every 5 turns
    SESSION_END_TIMEOUT = 30  # seconds
    ORPHAN_LOOKBACK_DAYS = 7

    # ------------------------------------------------------------------
    # Task 11.1 — pure helper
    # ------------------------------------------------------------------

    @staticmethod
    def should_checkpoint(turn_number: int) -> bool:
        """Return True if turn_number is a positive multiple of 5."""
        return turn_number > 0 and turn_number % 5 == 0

    # ------------------------------------------------------------------
    # Task 11.2 — Phase 1: auto-checkpoint
    # ------------------------------------------------------------------

    async def auto_checkpoint(
        self,
        session_id: str,
        turn_number: int,
        messages: list[dict],
    ) -> None:
        """Overwrite session transcript and update last_checkpoint_turn.

        Fire-and-forget semantics: on failure retry once after 1s, never raise.
        Must complete within 2 seconds per attempt.
        """
        try:
            await self._write_checkpoint(session_id, turn_number, messages)
        except Exception as exc:
            logger.warning(
                "Checkpoint failed for session %s (attempt 1): %s",
                session_id,
                exc,
            )
            try:
                await asyncio.sleep(1)
                await self._write_checkpoint(session_id, turn_number, messages)
            except Exception as retry_exc:
                logger.error(
                    "Checkpoint retry failed for session %s: %s",
                    session_id,
                    retry_exc,
                )
                # Never raise — fire-and-forget

    async def _write_checkpoint(
        self,
        session_id: str,
        turn_number: int,
        messages: list[dict],
    ) -> None:
        """Perform the actual MongoDB write for a checkpoint."""
        sessions = get_sessions_collection()
        await sessions.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "transcript": messages,
                    "last_checkpoint_turn": turn_number,
                }
            },
        )

    # ------------------------------------------------------------------
    # Task 11.3 — Phase 2: clean session end
    # ------------------------------------------------------------------

    async def end_session(self, session_id: str, user_id: str) -> None:
        """Invoke summarization LLM and route outputs through SessionEndProcessor.

        On LLM failure/timeout → mark session 'orphaned', preserve transcript.
        """
        sessions = get_sessions_collection()
        settings = get_settings()

        # Fetch the session transcript for summarization
        session_doc = await sessions.find_one({"session_id": session_id})
        transcript = session_doc.get("transcript", []) if session_doc else []

        try:
            llm_output = await self._call_summarization_llm(
                transcript, settings
            )

            # Route through SessionEndProcessor
            processor = SessionEndProcessor()
            await processor.process(user_id, session_id, llm_output)

            # Mark session as ended
            await sessions.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "ended_at": datetime.now(UTC),
                        "summary": llm_output.get("narrative_summary"),
                    }
                },
            )

        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.error(
                "LLM call failed for session %s: %s", session_id, exc
            )
            await sessions.update_one(
                {"session_id": session_id},
                {"$set": {"orphaned": True}},
            )
        except Exception as exc:
            logger.error(
                "Unexpected error ending session %s: %s", session_id, exc
            )
            await sessions.update_one(
                {"session_id": session_id},
                {"$set": {"orphaned": True}},
            )

    # ------------------------------------------------------------------
    # Tasks 12.1–12.3 — Orphaned session recovery
    # ------------------------------------------------------------------

    async def recover_orphaned_sessions(self, user_id: str) -> None:
        """Recover orphaned sessions for a user.

        Query sessions with no ended_at, no summary, checkpoint data exists,
        created within last 7 days. Process each sequentially.
        Must complete all recoveries before returning (called at session start).
        """
        sessions = get_sessions_collection()
        settings = get_settings()
        cutoff = datetime.now(UTC) - timedelta(days=self.ORPHAN_LOOKBACK_DAYS)

        cursor = sessions.find(
            {
                "user_id": user_id,
                "ended_at": None,
                "summary": None,
                "transcript": {"$exists": True},
                "created_at": {"$gte": cutoff},
            }
        )

        orphaned_sessions = await cursor.to_list(length=None)

        for session_doc in orphaned_sessions:
            session_id = session_doc.get("session_id")
            transcript = session_doc.get("transcript", [])

            if not transcript:
                continue

            try:
                llm_output = await self._call_summarization_llm(
                    transcript, settings
                )

                # Route through SessionEndProcessor
                processor = SessionEndProcessor()
                await processor.process(user_id, session_id, llm_output)

                # Mark as recovered and ended
                await sessions.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "ended_at": datetime.now(UTC),
                            "recovered": True,
                            "summary": llm_output.get("narrative_summary"),
                        }
                    },
                )

                logger.info(
                    "Recovered orphaned session %s for user %s",
                    session_id,
                    user_id,
                )

            except Exception as exc:
                logger.warning(
                    "Failed to recover session %s: %s — retaining for next attempt",
                    session_id,
                    exc,
                )
                # Skip and retain for next retry

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_summarization_llm(
        self,
        transcript: list[dict],
        settings,
    ) -> dict:
        """Call the summarization LLM endpoint with the session transcript.

        Returns the parsed JSON response containing narrative_summary and skill_update.
        Raises httpx.TimeoutException or httpx.HTTPStatusError on failure.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.SESSION_END_TIMEOUT)
        ) as client:
            response = await client.post(
                settings.LLM_ENDPOINT,
                json={"transcript": transcript},
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()
