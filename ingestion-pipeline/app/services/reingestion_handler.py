"""Re-ingestion handler implementing full replace semantics with rollback on failure.

Handles re-uploads by:
1. Backing up existing data for the source category
2. Deleting existing data for the source category (preserving session-tagged data)
3. Running the normal ingestion pipeline for new files
4. If failure → restoring backed-up data and marking job failed
5. If success → updating job with last_reingested_at timestamp
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config.database import (
    get_embeddings_collection,
    get_ingestion_jobs_collection,
    get_skill_graph_collection,
    get_users_collection,
)
from app.models.schemas import IngestionFile
from app.services.extractor_service import ExtractorService
from app.services.ingestion_router import IngestionRouter

logger = logging.getLogger(__name__)


@dataclass
class BackupData:
    """Holds backed-up data for potential rollback during re-ingestion."""

    embedding_docs: list[dict] = field(default_factory=list)
    skill_graph_docs: list[dict] = field(default_factory=list)
    profile_fields: dict | None = None


class ReIngestionHandler:
    """Handle re-uploads with full replace semantics and rollback on failure.

    Flow:
      1. Back up existing data for source_category
      2. Delete existing data for source_category (preserve session-tagged data)
      3. Run normal ingestion pipeline (ExtractorService → IngestionRouter)
      4. If success → update job with last_reingested_at, mark done
      5. If failure → restore backed-up data, mark job failed
    """

    def __init__(self) -> None:
        self._extractor_service = ExtractorService()
        self._ingestion_router = IngestionRouter()

    async def handle(
        self,
        user_id: str,
        source_category: str,
        files: list[IngestionFile],
        job_id: str,
    ) -> None:
        """Execute re-ingestion for a given source category.

        Args:
            user_id: The user who owns the data.
            source_category: The source category being re-ingested ('resume' or 'leetcode').
            files: List of new files to ingest.
            job_id: The ingestion job identifier.
        """
        logger.info(
            "Starting re-ingestion for user %s, source_category '%s', job %s",
            user_id,
            source_category,
            job_id,
        )

        # Step 1: Back up existing data
        backup = await self._backup_existing_data(user_id, source_category)
        logger.info(
            "Backed up %d embedding docs, %d skill graph docs for rollback.",
            len(backup.embedding_docs),
            len(backup.skill_graph_docs),
        )

        # Step 2: Delete existing data for source_category
        await self._delete_old_data(user_id, source_category)
        logger.info("Deleted old data for source_category '%s'.", source_category)

        # Step 3: Run new ingestion pipeline
        try:
            extraction_result = await self._extractor_service.extract(job_id, files)
            await self._ingestion_router.route(extraction_result, job_id, user_id)
        except Exception as exc:
            # Step 5 (failure path): Restore backed-up data
            logger.error(
                "Re-ingestion pipeline failed for job %s: %s. Restoring backup.",
                job_id,
                exc,
            )
            await self._rollback(user_id, source_category, backup)
            await self._mark_job_failed(job_id, f"Re-ingestion failed: {exc}")
            return

        # Step 4 (success path): Update job with last_reingested_at
        await self._mark_job_success(job_id)
        logger.info("Re-ingestion completed successfully for job %s.", job_id)

    async def _backup_existing_data(
        self, user_id: str, source_category: str
    ) -> BackupData:
        """Back up existing data for the source category before deletion.

        Backs up:
        - All embedding documents matching user_id AND source_category
        - All skill graph documents affected by this source category
        - Core profile ingestion fields (for resume source)

        Args:
            user_id: The user who owns the data.
            source_category: The source category ('resume' or 'leetcode').

        Returns:
            BackupData containing all backed-up documents.
        """
        backup = BackupData()

        # Back up embeddings for this source category
        embeddings_collection = get_embeddings_collection()
        cursor = embeddings_collection.find(
            {
                "metadata.user_id": user_id,
                "metadata.source": source_category,
            }
        )
        backup.embedding_docs = await cursor.to_list(length=None)

        # Back up structured data based on source category
        if source_category == "leetcode":
            # Back up skill graph docs with leetcode_solved signals
            skill_graph_collection = get_skill_graph_collection()
            sg_cursor = skill_graph_collection.find(
                {
                    "user_id": user_id,
                    "signals.leetcode_solved": {"$exists": True},
                }
            )
            backup.skill_graph_docs = await sg_cursor.to_list(length=None)

        elif source_category == "resume":
            # Back up core profile ingestion fields
            users_collection = get_users_collection()
            user_doc = await users_collection.find_one({"user_id": user_id})
            if user_doc:
                backup.profile_fields = {
                    "current_role": user_doc.get("current_role"),
                    "years_of_experience": user_doc.get("years_of_experience"),
                    "education": user_doc.get("education"),
                    "skills": user_doc.get("skills", []),
                }

            # Also back up any skill graph docs from resume (skills-based entries)
            skill_graph_collection = get_skill_graph_collection()
            sg_cursor = skill_graph_collection.find(
                {
                    "user_id": user_id,
                    "source": "resume",
                }
            )
            backup.skill_graph_docs = await sg_cursor.to_list(length=None)

        return backup

    async def _delete_old_data(self, user_id: str, source_category: str) -> None:
        """Delete all data for the given source category, preserving session-tagged data.

        Deletes:
        - All embedding docs where metadata.source matches source_category
          (session_summary and session sources are NEVER deleted)
        - Structured data originating from that source category

        Args:
            user_id: The user who owns the data.
            source_category: The source category to delete ('resume' or 'leetcode').
        """
        # Delete embeddings for this source category (preserves session/session_summary)
        embeddings_collection = get_embeddings_collection()
        delete_result = await embeddings_collection.delete_many(
            {
                "metadata.user_id": user_id,
                "metadata.source": source_category,
            }
        )
        logger.info(
            "Deleted %d embedding documents for source '%s'.",
            delete_result.deleted_count,
            source_category,
        )

        # Delete structured data
        if source_category == "leetcode":
            # Delete skill graph documents with leetcode_solved signals for this user
            skill_graph_collection = get_skill_graph_collection()
            sg_result = await skill_graph_collection.delete_many(
                {
                    "user_id": user_id,
                    "signals.leetcode_solved": {"$exists": True},
                }
            )
            logger.info(
                "Deleted %d skill graph docs (leetcode) for user %s.",
                sg_result.deleted_count,
                user_id,
            )

        elif source_category == "resume":
            # Clear core profile ingestion fields (set to None/empty)
            users_collection = get_users_collection()
            await users_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "current_role": None,
                        "years_of_experience": None,
                        "education": None,
                        "skills": [],
                    }
                },
            )
            logger.info("Cleared core profile ingestion fields for user %s.", user_id)

            # Delete any resume-sourced skill graph entries
            skill_graph_collection = get_skill_graph_collection()
            sg_result = await skill_graph_collection.delete_many(
                {
                    "user_id": user_id,
                    "source": "resume",
                }
            )
            logger.info(
                "Deleted %d resume-sourced skill graph docs for user %s.",
                sg_result.deleted_count,
                user_id,
            )

    async def _rollback(
        self, user_id: str, source_category: str, backup: BackupData
    ) -> None:
        """Restore previously deleted data from the backup.

        Args:
            user_id: The user who owns the data.
            source_category: The source category that was being re-ingested.
            backup: The BackupData containing documents to restore.
        """
        logger.info("Rolling back re-ingestion for user %s, source '%s'.", user_id, source_category)

        try:
            # Restore embeddings
            if backup.embedding_docs:
                embeddings_collection = get_embeddings_collection()
                await embeddings_collection.insert_many(backup.embedding_docs)
                logger.info(
                    "Restored %d embedding documents.", len(backup.embedding_docs)
                )

            # Restore structured data
            if source_category == "leetcode" and backup.skill_graph_docs:
                skill_graph_collection = get_skill_graph_collection()
                await skill_graph_collection.insert_many(backup.skill_graph_docs)
                logger.info(
                    "Restored %d skill graph documents.", len(backup.skill_graph_docs)
                )

            elif source_category == "resume":
                # Restore core profile fields
                if backup.profile_fields:
                    users_collection = get_users_collection()
                    await users_collection.update_one(
                        {"user_id": user_id},
                        {"$set": backup.profile_fields},
                    )
                    logger.info("Restored core profile fields for user %s.", user_id)

                # Restore resume-sourced skill graph docs
                if backup.skill_graph_docs:
                    skill_graph_collection = get_skill_graph_collection()
                    await skill_graph_collection.insert_many(backup.skill_graph_docs)
                    logger.info(
                        "Restored %d resume skill graph documents.",
                        len(backup.skill_graph_docs),
                    )

        except Exception as rollback_exc:
            # Rollback itself failed — log critical error but don't raise
            logger.critical(
                "ROLLBACK FAILED for user %s, source '%s': %s. "
                "Data may be in an inconsistent state. Manual intervention required.",
                user_id,
                source_category,
                rollback_exc,
            )

    async def _mark_job_failed(self, job_id: str, error_message: str) -> None:
        """Mark the job as failed with an error message.

        Args:
            job_id: The ingestion job identifier.
            error_message: User-facing error description.
        """
        collection = get_ingestion_jobs_collection()
        await collection.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": error_message,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        logger.info("Marked re-ingestion job %s as failed.", job_id)

    async def _mark_job_success(self, job_id: str) -> None:
        """Mark the job as done with last_reingested_at timestamp.

        Args:
            job_id: The ingestion job identifier.
        """
        now = datetime.now(UTC)
        collection = get_ingestion_jobs_collection()
        await collection.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "done",
                    "last_reingested_at": now.isoformat(),
                    "structured_done": True,
                    "embedding_done": True,
                    "updated_at": now,
                    "completed_at": now,
                }
            },
        )
        logger.info("Marked re-ingestion job %s as done.", job_id)
