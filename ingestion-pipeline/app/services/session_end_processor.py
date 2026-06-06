"""SessionEndProcessor: processes LLM session-end output (narrative_summary + skill_update)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.config.database import get_sessions_collection, get_skill_graph_collection
from app.models.schemas import Chunk, ChunkMetadata
from app.models.validators import ValidationError, validate_skill_graph_signals
from app.services.embedder_service import EmbedderService, EmbeddingError

logger = logging.getLogger(__name__)


class SessionEndProcessor:
    """Process LLM session-end output: embed narrative summary and upsert skill updates.

    Handles partial failures gracefully:
    - If embedding fails, skill update is still attempted.
    - If skill validation fails, embedding result is unaffected.
    - If LLM output is malformed, session is marked orphaned.
    """

    async def process(
        self,
        user_id: str,
        session_id: str,
        llm_output: dict,
    ) -> None:
        """Process session-end LLM output.

        Args:
            user_id: The user who owns the session.
            session_id: The session being ended.
            llm_output: Raw dict from LLM containing narrative_summary and skill_update.
        """
        sessions_collection = get_sessions_collection()

        # --- Task 10.2: Input validation ---
        if not self._is_valid_output(llm_output):
            logger.warning(
                "Malformed LLM output for session %s: missing narrative_summary or skill_update",
                session_id,
            )
            await sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"orphaned": True}},
            )
            return

        narrative_summary: str = llm_output["narrative_summary"]
        skill_update: dict = llm_output["skill_update"]

        # --- Task 10.3: Narrative embedding ---
        embedding_failed = False
        try:
            chunk = self._build_narrative_chunk(user_id, session_id, llm_output)
            embedder = EmbedderService()
            await embedder.embed_and_store([chunk])
        except EmbeddingError as e:
            logger.error(
                "Embedding failed for session %s: %s", session_id, str(e)
            )
            embedding_failed = True

        # --- Task 10.4: Skill update ---
        try:
            validated_signals = validate_skill_graph_signals(skill_update)
            topic = skill_update.get("topic")
            if topic:
                skill_graph_collection = get_skill_graph_collection()
                signals_data = validated_signals.model_dump(exclude_none=True)
                await skill_graph_collection.update_one(
                    {"user_id": user_id, "topic": topic},
                    {"$set": signals_data},
                    upsert=True,
                )
            else:
                logger.warning(
                    "Skill update for session %s has no topic, skipping write",
                    session_id,
                )
        except ValidationError as e:
            logger.error(
                "Skill update validation failed for session %s: %s",
                session_id,
                str(e),
            )

        # --- Task 10.5: Partial failure handling ---
        if embedding_failed:
            await sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"partial": True}},
            )

    def _is_valid_output(self, llm_output: dict) -> bool:
        """Check that llm_output has required fields with correct types.

        Args:
            llm_output: Raw dict from LLM.

        Returns:
            True if output has narrative_summary (str) and skill_update (dict).
        """
        if not isinstance(llm_output, dict):
            return False
        if "narrative_summary" not in llm_output:
            return False
        if "skill_update" not in llm_output:
            return False
        if not isinstance(llm_output["narrative_summary"], str):
            return False
        if not isinstance(llm_output["skill_update"], dict):
            return False
        return True

    def _build_narrative_chunk(
        self, user_id: str, session_id: str, llm_output: dict
    ) -> Chunk:
        """Build a Chunk from the narrative summary with session metadata.

        Args:
            user_id: The user who owns the session.
            session_id: The session being ended.
            llm_output: Raw dict containing narrative_summary and optional metadata fields.

        Returns:
            A Chunk ready for embedding.
        """
        today_iso = datetime.now(UTC).strftime("%Y-%m-%d")

        metadata = ChunkMetadata(
            user_id=user_id,
            source="session_summary",
            session_id=session_id,
            date=today_iso,
            type=llm_output.get("type", "general"),
            topic=llm_output.get("topic"),
            topic_category=llm_output.get("topic_category"),
            chunk_index=0,
        )

        return Chunk(
            text=llm_output["narrative_summary"],
            metadata=metadata,
        )
