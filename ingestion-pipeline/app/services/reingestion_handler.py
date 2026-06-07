"""Re-ingestion handler implementing full replace semantics with rollback on failure.

Handles re-uploads by:
1. Backing up existing data for the source category
2. Deleting existing data for the source category based on upload context
3. Running the normal ingestion pipeline for new files
4. If failure → restoring backed-up data and marking job failed
5. If success → updating job with last_reingested_at timestamp

Session upload context handling:
- When upload_context="session" and prior data is from onboarding:
  Delete only onboarding-tagged chunks/facts for that category.
  Preserve all session-tagged data.
- When upload_context="session" and prior data is from a prior session upload:
  Replace prior session-category data.
  Preserve onboarding data and other-category session data.
- When upload_context is None (onboarding re-upload):
  Original behavior — delete all data for the source category (preserves session-tagged data).
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
      1. Back up existing data for source_category (scoped by upload_context)
      2. Delete existing data for source_category (scoped by upload_context)
      3. Run normal ingestion pipeline (ExtractorService → IngestionRouter)
      4. If success → update job with last_reingested_at, mark done
      5. If failure → restore backed-up data, mark job failed

    Session uploads are processed in FIFO order within the same job queue as
    onboarding uploads — no priority changes are applied.
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
        upload_context: str | None = None,
    ) -> None:
        """Execute re-ingestion for a given source category.

        Args:
            user_id: The user who owns the data.
            source_category: The source category being re-ingested ('resume' or 'leetcode').
            files: List of new files to ingest.
            job_id: The ingestion job identifier.
            upload_context: The context of the new upload — "session" for session uploads,
                None for onboarding uploads.
        """
        logger.info(
            "Starting re-ingestion for user %s, source_category '%s', job %s, upload_context=%s",
            user_id,
            source_category,
            job_id,
            upload_context,
        )

        # Step 1: Back up existing data (scoped by upload_context)
        backup = await self._backup_existing_data(user_id, source_category, upload_context)
        logger.info(
            "Backed up %d embedding docs, %d skill graph docs for rollback.",
            len(backup.embedding_docs),
            len(backup.skill_graph_docs),
        )

        # Step 2: Delete existing data for source_category (scoped by upload_context)
        await self._delete_old_data(user_id, source_category, upload_context)
        logger.info("Deleted old data for source_category '%s', upload_context=%s.", source_category, upload_context)

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
        self, user_id: str, source_category: str, upload_context: str | None = None
    ) -> BackupData:
        """Back up existing data for the source category before deletion.

        The scope of the backup depends on upload_context:
        - upload_context=None (onboarding re-upload): backs up ALL data for source_category
          that is NOT session-tagged (original behavior).
        - upload_context="session" with prior onboarding data: backs up only onboarding-tagged
          data for that category.
        - upload_context="session" with prior session data: backs up only session-tagged data
          for that source category.

        Args:
            user_id: The user who owns the data.
            source_category: The source category ('resume' or 'leetcode').
            upload_context: "session" for session uploads, None for onboarding.

        Returns:
            BackupData containing all backed-up documents.
        """
        backup = BackupData()

        embeddings_collection = get_embeddings_collection()

        if upload_context == "session":
            # Session upload: determine what prior data exists and back up accordingly.
            # First check if there's prior session data for this category
            prior_session_filter = {
                "metadata.user_id": user_id,
                "metadata.source": source_category,
                "metadata.upload_context": "session",
            }
            prior_session_count = await embeddings_collection.count_documents(prior_session_filter)

            if prior_session_count > 0:
                # Prior session data exists for this category — back up only session data
                cursor = embeddings_collection.find(prior_session_filter)
                backup.embedding_docs = await cursor.to_list(length=None)
            else:
                # No prior session data — back up onboarding data for this category
                prior_onboarding_filter = {
                    "metadata.user_id": user_id,
                    "metadata.source": source_category,
                    "metadata.upload_context": {"$ne": "session"},
                }
                cursor = embeddings_collection.find(prior_onboarding_filter)
                backup.embedding_docs = await cursor.to_list(length=None)

            # Back up structured data based on source category
            if source_category == "leetcode":
                skill_graph_collection = get_skill_graph_collection()
                if prior_session_count > 0:
                    # Back up session-tagged leetcode skill graph docs
                    sg_cursor = skill_graph_collection.find(
                        {
                            "user_id": user_id,
                            "signals.leetcode_solved": {"$exists": True},
                            "upload_context": "session",
                        }
                    )
                else:
                    # Back up onboarding-tagged leetcode skill graph docs
                    sg_cursor = skill_graph_collection.find(
                        {
                            "user_id": user_id,
                            "signals.leetcode_solved": {"$exists": True},
                            "upload_context": {"$ne": "session"},
                        }
                    )
                backup.skill_graph_docs = await sg_cursor.to_list(length=None)

            elif source_category == "resume":
                if prior_session_count > 0:
                    # Back up session-tagged resume skill graph entries
                    skill_graph_collection = get_skill_graph_collection()
                    sg_cursor = skill_graph_collection.find(
                        {
                            "user_id": user_id,
                            "source": "resume",
                            "upload_context": "session",
                        }
                    )
                    backup.skill_graph_docs = await sg_cursor.to_list(length=None)
                else:
                    # Back up onboarding-tagged profile fields and skill graph
                    users_collection = get_users_collection()
                    user_doc = await users_collection.find_one({"user_id": user_id})
                    if user_doc:
                        backup.profile_fields = {
                            "current_role": user_doc.get("current_role"),
                            "years_of_experience": user_doc.get("years_of_experience"),
                            "education": user_doc.get("education"),
                            "skills": user_doc.get("skills", []),
                        }

                    skill_graph_collection = get_skill_graph_collection()
                    sg_cursor = skill_graph_collection.find(
                        {
                            "user_id": user_id,
                            "source": "resume",
                            "upload_context": {"$ne": "session"},
                        }
                    )
                    backup.skill_graph_docs = await sg_cursor.to_list(length=None)
        else:
            # Onboarding re-upload: original behavior — back up all non-session data
            cursor = embeddings_collection.find(
                {
                    "metadata.user_id": user_id,
                    "metadata.source": source_category,
                }
            )
            backup.embedding_docs = await cursor.to_list(length=None)

            if source_category == "leetcode":
                skill_graph_collection = get_skill_graph_collection()
                sg_cursor = skill_graph_collection.find(
                    {
                        "user_id": user_id,
                        "signals.leetcode_solved": {"$exists": True},
                    }
                )
                backup.skill_graph_docs = await sg_cursor.to_list(length=None)

            elif source_category == "resume":
                users_collection = get_users_collection()
                user_doc = await users_collection.find_one({"user_id": user_id})
                if user_doc:
                    backup.profile_fields = {
                        "current_role": user_doc.get("current_role"),
                        "years_of_experience": user_doc.get("years_of_experience"),
                        "education": user_doc.get("education"),
                        "skills": user_doc.get("skills", []),
                    }

                skill_graph_collection = get_skill_graph_collection()
                sg_cursor = skill_graph_collection.find(
                    {
                        "user_id": user_id,
                        "source": "resume",
                    }
                )
                backup.skill_graph_docs = await sg_cursor.to_list(length=None)

        return backup

    async def _delete_old_data(self, user_id: str, source_category: str, upload_context: str | None = None) -> None:
        """Delete existing data for the given source category, scoped by upload context.

        Behavior depends on upload_context:
        - upload_context=None (onboarding re-upload):
          Deletes all embedding docs where metadata.source matches source_category
          (session and session_summary sources are NEVER deleted).
          Deletes structured data for that source category.

        - upload_context="session" with prior onboarding data for same category:
          Deletes ONLY onboarding-tagged chunks/facts for that category
          (upload_context != "session"). Preserves ALL session-tagged data.

        - upload_context="session" with prior session data for same category:
          Deletes ONLY prior session-tagged chunks/facts for that category
          (upload_context == "session"). Preserves onboarding data and
          other-category session data.

        Args:
            user_id: The user who owns the data.
            source_category: The source category to delete ('resume' or 'leetcode').
            upload_context: "session" for session uploads, None for onboarding.
        """
        embeddings_collection = get_embeddings_collection()

        if upload_context == "session":
            # Session upload: determine whether prior data is session or onboarding
            prior_session_filter = {
                "metadata.user_id": user_id,
                "metadata.source": source_category,
                "metadata.upload_context": "session",
            }
            prior_session_count = await embeddings_collection.count_documents(prior_session_filter)

            if prior_session_count > 0:
                # Prior session data exists → replace session data for this category
                embed_delete_filter = {
                    "metadata.user_id": user_id,
                    "metadata.source": source_category,
                    "metadata.upload_context": "session",
                }
            else:
                # No prior session data → delete onboarding data for this category
                embed_delete_filter = {
                    "metadata.user_id": user_id,
                    "metadata.source": source_category,
                    "metadata.upload_context": {"$ne": "session"},
                }

            delete_result = await embeddings_collection.delete_many(embed_delete_filter)
            logger.info(
                "Deleted %d embedding documents for source '%s' (upload_context=%s, targeting=%s).",
                delete_result.deleted_count,
                source_category,
                upload_context,
                "session" if prior_session_count > 0 else "onboarding",
            )

            # Delete structured data scoped by context
            if source_category == "leetcode":
                skill_graph_collection = get_skill_graph_collection()
                if prior_session_count > 0:
                    # Delete only session-tagged leetcode skill graph docs
                    sg_result = await skill_graph_collection.delete_many(
                        {
                            "user_id": user_id,
                            "signals.leetcode_solved": {"$exists": True},
                            "upload_context": "session",
                        }
                    )
                else:
                    # Delete only onboarding-tagged leetcode skill graph docs
                    sg_result = await skill_graph_collection.delete_many(
                        {
                            "user_id": user_id,
                            "signals.leetcode_solved": {"$exists": True},
                            "upload_context": {"$ne": "session"},
                        }
                    )
                logger.info(
                    "Deleted %d skill graph docs (leetcode) for user %s (targeting=%s).",
                    sg_result.deleted_count,
                    user_id,
                    "session" if prior_session_count > 0 else "onboarding",
                )

            elif source_category == "resume":
                if prior_session_count > 0:
                    # Delete only session-tagged resume skill graph entries
                    # Do NOT clear core profile fields (those are onboarding-owned)
                    skill_graph_collection = get_skill_graph_collection()
                    sg_result = await skill_graph_collection.delete_many(
                        {
                            "user_id": user_id,
                            "source": "resume",
                            "upload_context": "session",
                        }
                    )
                    logger.info(
                        "Deleted %d session-tagged resume skill graph docs for user %s.",
                        sg_result.deleted_count,
                        user_id,
                    )
                else:
                    # Delete onboarding-tagged resume data: clear core profile fields
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

                    # Delete onboarding-tagged resume-sourced skill graph entries
                    skill_graph_collection = get_skill_graph_collection()
                    sg_result = await skill_graph_collection.delete_many(
                        {
                            "user_id": user_id,
                            "source": "resume",
                            "upload_context": {"$ne": "session"},
                        }
                    )
                    logger.info(
                        "Deleted %d onboarding-tagged resume skill graph docs for user %s.",
                        sg_result.deleted_count,
                        user_id,
                    )
        else:
            # Onboarding re-upload: original behavior
            # Delete embeddings for this source category (preserves session/session_summary)
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
