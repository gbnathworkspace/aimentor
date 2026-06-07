"""Session context hook for creating and deactivating ImmediateContext documents.

This service bridges the Python ingestion pipeline with the ImmediateContext
system used by the TypeScript Context Assembler. Both services share the same
MongoDB database, so direct writes avoid the need for inter-service HTTP calls.

Hooks:
- Post-extraction: Creates an ImmediateContext document after extraction completes
  for session-uploaded files (upload_context == "session").
- Post-ingestion: Deactivates the ImmediateContext when full ingestion completes
  (job status reaches "done").
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.config.database import get_immediate_contexts_collection, get_ingestion_jobs_collection
from app.models.schemas import LeetCodeTopicStats
from app.services.extractor_service import ExtractionResult

logger = logging.getLogger(__name__)


def _summarize_leetcode_stats(stats: list[LeetCodeTopicStats]) -> str:
    """Convert LeetCode topic stats into a human-readable summary.

    Mirrors the TypeScript `summarizeLeetCodeStats()` function in
    session-context-injector.ts.

    Format:
        LeetCode Summary:
        - Arrays: 12 easy, 5 medium, 1 hard (18 total)
        - Graphs: 4 easy, 2 medium, 0 hard (6 total)
    """
    lines = []
    for stat in stats:
        total = stat.easy + stat.medium + stat.hard
        lines.append(
            f"- {stat.topic}: {stat.easy} easy, {stat.medium} medium, {stat.hard} hard ({total} total)"
        )
    return f"LeetCode Summary:\n" + "\n".join(lines)


def _extract_text_from_resume_sections(extraction_result: ExtractionResult) -> str:
    """Concatenate all resume section texts into a single string for ImmediateContext."""
    if not extraction_result.resume_sections:
        return ""
    return "\n\n".join(
        f"{section.section}:\n{section.text}"
        for section in extraction_result.resume_sections
    )


class SessionContextHook:
    """Hooks into the ingestion pipeline for session-uploaded files.

    Creates and deactivates ImmediateContext documents directly in MongoDB,
    which the TypeScript ContextAssembler reads on every LLM call.
    """

    async def after_extraction(
        self,
        job_id: str,
        user_id: str,
        extraction_result: ExtractionResult,
        job_record: dict,
    ) -> None:
        """Called after extraction completes for a session-uploaded file.

        Creates an ImmediateContext document in MongoDB and updates the
        JobRecord with extraction_ready: true.

        Args:
            job_id: The ingestion job identifier.
            user_id: The user who owns the upload.
            extraction_result: The extracted content from the file.
            job_record: The full job record dict from MongoDB (contains session metadata).
        """
        session_id = job_record.get("session_id")
        upload_context = job_record.get("upload_context")

        if upload_context != "session" or not session_id:
            return

        # Determine file type and content
        filename = ""
        file_type = ""
        content = ""

        files = job_record.get("files", [])
        if files:
            first_file = files[0]
            filename = first_file.get("filename", "")

        if extraction_result.leetcode_stats:
            file_type = "leetcode"
            content = _summarize_leetcode_stats(extraction_result.leetcode_stats)
        elif extraction_result.resume_sections:
            file_type = "resume"
            content = _extract_text_from_resume_sections(extraction_result)
        else:
            logger.warning(
                "No extracted content for session job %s — skipping ImmediateContext creation.",
                job_id,
            )
            return

        # Token count estimation (simple word-based approximation since
        # tiktoken is not available in Python; the TypeScript side does
        # precise truncation when reading, and the content is stored as-is)
        # For a more accurate count we estimate ~0.75 tokens per character
        # but this field is informational; truncation is handled by the TS service.
        token_count = max(1, len(content.split()) * 4 // 3)

        accompanying_message = job_record.get("accompanying_message", "") or ""

        now = datetime.now(UTC)
        doc = {
            "sessionId": session_id,
            "userId": user_id,
            "jobId": job_id,
            "filename": filename,
            "fileType": file_type,
            "content": content,
            "tokenCount": token_count,
            "accompanyingMessage": accompanying_message,
            "active": True,
            "createdAt": now,
            "updatedAt": now,
        }

        # Attempt to write (with one retry on failure)
        collection = get_immediate_contexts_collection()
        write_succeeded = False

        try:
            await collection.insert_one(doc)
            write_succeeded = True
        except Exception as exc:
            logger.warning(
                "First ImmediateContext write failed for job %s: %s. Retrying...",
                job_id,
                exc,
            )
            try:
                await collection.insert_one(doc)
                write_succeeded = True
            except Exception as retry_exc:
                logger.error(
                    "ImmediateContext write retry failed for job %s: %s",
                    job_id,
                    retry_exc,
                )

        if not write_succeeded:
            # Mark job as failed
            jobs_collection = get_ingestion_jobs_collection()
            await jobs_collection.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": "Immediate context storage was unsuccessful",
                        "updated_at": datetime.now(UTC),
                    }
                },
            )
            logger.error(
                "Marked job %s as failed due to ImmediateContext write failure.", job_id
            )
            return

        # Update JobRecord with extraction_ready: true
        jobs_collection = get_ingestion_jobs_collection()
        await jobs_collection.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "extraction_ready": True,
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        logger.info(
            "Created ImmediateContext for session job %s (file_type=%s, tokens=%d).",
            job_id,
            file_type,
            token_count,
        )

    async def after_ingestion_complete(self, job_id: str) -> None:
        """Called after full ingestion completes (job status reaches 'done').

        Deactivates the ImmediateContext by setting active: false.
        After deactivation, the content is served exclusively through Episodic RAG.

        Args:
            job_id: The ingestion job identifier.
        """
        collection = get_immediate_contexts_collection()
        result = await collection.update_one(
            {"jobId": job_id},
            {"$set": {"active": False, "updatedAt": datetime.now(UTC)}},
        )

        if result.modified_count > 0:
            logger.info(
                "Deactivated ImmediateContext for job %s.", job_id
            )
        else:
            # No ImmediateContext found — this is normal for non-session uploads
            logger.debug(
                "No ImmediateContext to deactivate for job %s (may not be a session upload).",
                job_id,
            )
