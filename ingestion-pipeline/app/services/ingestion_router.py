"""Ingestion router that splits extracted content into structured and narrative paths."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config.database import get_ingestion_jobs_collection
from app.models.schemas import LeetCodeTopicStats, ResumeSection
from app.services.chunker_service import ChunkerService
from app.services.embedder_service import EmbedderService
from app.services.extractor_service import ExtractionResult
from app.services.session_context_hook import SessionContextHook
from app.services.structured_parser import StructuredParser

logger = logging.getLogger(__name__)

# Sections routed to the structured path
STRUCTURED_SECTIONS = {"work_experience", "skills", "education"}

# Sections routed to the narrative path
NARRATIVE_SECTIONS = {"work_experience", "projects"}


@dataclass
class RoutedContent:
    """Content routed to structured and narrative paths."""

    structured_leetcode: list[LeetCodeTopicStats] | None = None
    structured_sections: list[ResumeSection] | None = None
    narrative_sections: list[ResumeSection] | None = None


class IngestionRouter:
    """Splits extracted content into structured and narrative paths based on routing rules.

    Routing rules:
      - LeetCode stats → structured path only
      - work_experience → both structured AND narrative paths
      - skills → structured path only
      - projects → narrative path only
      - education → structured path only
      - unrecognized/other sections → discard + log warning

    After routing, runs structured and narrative paths in parallel using asyncio.gather.
    Error handling:
      - If structured path fails → mark job 'failed', don't run narrative
      - If narrative fails after structured succeeds → mark job 'partial'
      - On both success → mark job 'done'
    """

    def _route_content(self, extraction_result: ExtractionResult) -> RoutedContent:
        """Apply routing rules to the extraction result.

        This is a pure function suitable for unit testing.

        Args:
            extraction_result: Combined extraction output from all files.

        Returns:
            RoutedContent with content split into structured and narrative buckets.
        """
        routed = RoutedContent()

        # Route LeetCode stats to structured path only
        if extraction_result.leetcode_stats:
            routed.structured_leetcode = extraction_result.leetcode_stats

        # Route resume sections based on section type
        if extraction_result.resume_sections:
            structured_sections: list[ResumeSection] = []
            narrative_sections: list[ResumeSection] = []

            for section in extraction_result.resume_sections:
                section_name = section.section.lower().strip()

                if section_name in STRUCTURED_SECTIONS and section_name in NARRATIVE_SECTIONS:
                    # work_experience goes to both paths
                    structured_sections.append(section)
                    narrative_sections.append(section)
                elif section_name in STRUCTURED_SECTIONS:
                    # skills, education → structured only
                    structured_sections.append(section)
                elif section_name in NARRATIVE_SECTIONS:
                    # projects → narrative only
                    narrative_sections.append(section)
                else:
                    # Unrecognized section → discard + log warning
                    logger.warning(
                        "Discarding unrecognized section '%s' — does not match any routing rule.",
                        section.section,
                    )

            routed.structured_sections = structured_sections if structured_sections else None
            routed.narrative_sections = narrative_sections if narrative_sections else None

        return routed

    async def route(
        self, extraction_result: ExtractionResult, job_id: str, user_id: str
    ) -> None:
        """Route extracted content and execute structured/narrative paths in parallel.

        Args:
            extraction_result: Combined extraction output from all files.
            job_id: The ingestion job identifier.
            user_id: The user who owns this job.
        """
        # Hook: after extraction, create ImmediateContext for session uploads
        session_hook = SessionContextHook()
        collection = get_ingestion_jobs_collection()
        job_record = await collection.find_one({"job_id": job_id})

        if job_record and job_record.get("upload_context") == "session":
            await session_hook.after_extraction(
                job_id=job_id,
                user_id=user_id,
                extraction_result=extraction_result,
                job_record=job_record,
            )
            # If the hook marked the job as failed, stop processing
            refreshed_job = await collection.find_one({"job_id": job_id})
            if refreshed_job and refreshed_job.get("status") == "failed":
                logger.error(
                    "ImmediateContext creation failed for job %s — aborting pipeline.",
                    job_id,
                )
                return

        routed = self._route_content(extraction_result)

        # Run structured and narrative paths in parallel
        results = await asyncio.gather(
            self._run_structured_path(routed, user_id, job_id),
            self._run_narrative_path(routed, user_id, job_id),
            return_exceptions=True,
        )

        structured_result = results[0]
        narrative_result = results[1]

        # Check for failures
        if isinstance(structured_result, BaseException):
            logger.error(
                "Structured path failed for job %s: %s", job_id, structured_result
            )
            await self._update_job_status(job_id, "failed", str(structured_result))
            return

        if isinstance(narrative_result, BaseException):
            logger.error(
                "Narrative path failed for job %s (structured succeeded): %s",
                job_id,
                narrative_result,
            )
            await self._update_job_status(job_id, "partial")
            return

        # Both paths succeeded
        await self._update_job_status(job_id, "done")

        # Hook: after full ingestion completes, deactivate ImmediateContext
        if job_record and job_record.get("upload_context") == "session":
            await session_hook.after_ingestion_complete(job_id)

    async def _run_structured_path(
        self, routed: RoutedContent, user_id: str, job_id: str
    ) -> None:
        """Execute the structured path: StructuredParser → MongoDB."""
        if not routed.structured_leetcode and not routed.structured_sections:
            logger.info("Structured path: nothing to process for job %s", job_id)
            return

        parser = StructuredParser()
        await parser.process(
            leetcode_stats=routed.structured_leetcode,
            resume_sections=routed.structured_sections,
            user_id=user_id,
            job_id=job_id,
        )

    async def _run_narrative_path(
        self, routed: RoutedContent, user_id: str, job_id: str
    ) -> None:
        """Execute the narrative path: ChunkerService → EmbedderService → Atlas Vector Search."""
        if not routed.narrative_sections:
            logger.info("Narrative path: nothing to process for job %s", job_id)
            return

        chunker = ChunkerService()
        chunks = chunker.chunk(
            sections=routed.narrative_sections,
            user_id=user_id,
            source="resume",
            job_id=job_id,
        )

        if not chunks:
            logger.info("Narrative path: chunker produced 0 chunks for job %s", job_id)
            return

        logger.info(
            "Narrative path: embedding %d chunks for job %s", len(chunks), job_id
        )
        embedder = EmbedderService()
        await embedder.embed_and_store(chunks)

    async def _update_job_status(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        """Update the job status in MongoDB.

        Args:
            job_id: The ingestion job identifier.
            status: The new status value (done, partial, failed).
            error: Optional error message for failed jobs.
        """
        collection = get_ingestion_jobs_collection()
        update_fields: dict = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }

        if status == "done":
            update_fields["completed_at"] = datetime.now(UTC)
            update_fields["structured_done"] = True
            update_fields["embedding_done"] = True
        elif status == "partial":
            update_fields["structured_done"] = True
            update_fields["embedding_done"] = False
        elif status == "failed" and error:
            update_fields["error"] = error

        await collection.update_one(
            {"job_id": job_id},
            {"$set": update_fields},
        )
        logger.info("Updated job %s status to '%s'", job_id, status)
