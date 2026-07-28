"""Document upload pipeline orchestrator.

Coordinates the full background processing flow for chat document uploads:
extract → synthesize → create pending changes (or direct write if skip_review).

This is the main entry point for the BackgroundTasks function that drives
the Document Ingestion Pipeline. It is fully independent from the existing
IngestionService (onboarding pipeline).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.config.database import document_upload_jobs_col, profiles_col
from app.models.profile import PendingProfileChange, ProposableField
from app.services.document_extractor import extract_document
from app.services.l1_fact_synthesizer import synthesize_l1_facts

logger = logging.getLogger(__name__)


async def _update_job_status(
    job_id: str,
    status: str,
    extra_fields: dict | None = None,
) -> None:
    """Update the Upload_Job status and updated_at timestamp in MongoDB.

    Args:
        job_id: The Upload_Job ID.
        status: New status value.
        extra_fields: Additional fields to set alongside the status update.
    """
    update: dict = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if extra_fields:
        update.update(extra_fields)

    await document_upload_jobs_col().update_one(
        {"job_id": job_id},
        {"$set": update},
    )


async def _update_file_status(
    job_id: str,
    file_index: int,
    status: str,
    error: str | None = None,
) -> None:
    """Update the status of a specific file within the Upload_Job record.

    Args:
        job_id: The Upload_Job ID.
        file_index: Zero-based index of the file in the files array.
        status: New status for this file ('extracted' or 'failed').
        error: Error message if the file failed extraction.
    """
    update_fields: dict = {
        f"files.{file_index}.status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if error is not None:
        update_fields[f"files.{file_index}.error"] = error

    await document_upload_jobs_col().update_one(
        {"job_id": job_id},
        {"$set": update_fields},
    )


async def _create_pending_changes(
    user_id: str,
    job_id: str,
    proposals: list[dict],
) -> None:
    """Create PendingProfileChange entries for each proposal (skip_review=false).

    Each proposal becomes a PendingProfileChange entry tagged with
    source_type="document_upload" and session_id=job_id for traceability.

    Unlike the profiling agent (which replaces existing pending changes for the
    same field), document uploads APPEND proposals since multiple distinct
    proposals for the same field type are valid (e.g. multiple focus areas).

    Args:
        user_id: The authenticated user's ID.
        job_id: The Upload_Job ID (stored as session_id for traceability).
        proposals: List of proposal dicts from the synthesizer.
    """
    if not proposals:
        return

    now = datetime.now(timezone.utc)

    pending_entries: list[dict] = []
    for proposal in proposals:
        change = PendingProfileChange(
            field=ProposableField(proposal["field"]),
            proposed_value=proposal["proposed_value"],
            reason=proposal.get("reason", "Extracted from uploaded document")[:200],
            session_id=job_id,
            created_at=now,
            source_type="document_upload",
        )
        entry = change.model_dump(mode="json")
        # Carry over any extra flags (e.g. requires_replacement for style notes at cap)
        if proposal.get("requires_replacement"):
            entry["requires_replacement"] = True
        pending_entries.append(entry)

    # Append to existing pending_changes (do not replace other pending changes)
    await profiles_col().update_one(
        {"user_id": user_id},
        {
            "$push": {
                "pending_changes": {"$each": pending_entries},
            },
        },
    )

    logger.info(
        "Created %d PendingProfileChange entries for user_id=%s from job_id=%s",
        len(pending_entries),
        user_id,
        job_id,
    )


async def _apply_proposals_directly(
    user_id: str,
    proposals: list[dict],
) -> None:
    """Write proposals directly to L1 memory without pending changes (skip_review=true).

    Applies each proposal to the user's profile using the same logic as
    accept_pending_change in the profile router. This is the "trust the extraction"
    power-user path.

    Args:
        user_id: The authenticated user's ID.
        proposals: List of proposal dicts from the synthesizer.
    """
    if not proposals:
        return

    # Fetch current profile state for merging
    profile = await profiles_col().find_one({"user_id": user_id})
    if not profile:
        logger.warning(
            "Cannot apply proposals directly: profile not found for user_id=%s",
            user_id,
        )
        return

    update: dict[str, Any] = {}

    for proposal in proposals:
        field = proposal["field"]
        proposed_value = proposal["proposed_value"]

        if field == ProposableField.STYLE_NOTE.value:
            # Append new style note (respecting 5-note cap via FIFO drop-oldest)
            now = datetime.now(timezone.utc)
            new_note = {
                "category": proposed_value["category"],
                "note": proposed_value["note"],
                "source_quote": proposed_value.get("source_quote", ""),
                "session_id": "",  # No session for direct writes
                "added_at": now.isoformat(),
            }
            notes = list(profile.get("style_notes") or [])
            # If requires_replacement is set, we still add it (power user trusts it)
            notes.append(new_note)
            update["style_notes"] = notes[-5:]  # FIFO cap at 5

        elif field == ProposableField.FOCUS_AREA.value:
            # Append focus area (deduplication already done by synthesizer)
            focus_areas = list(update.get("focus_areas", profile.get("focus_areas") or []))
            new_area = proposed_value.get("value", "")
            if new_area and not any(
                existing.lower() == new_area.lower() for existing in focus_areas
            ):
                focus_areas.append(new_area)
            update["focus_areas"] = focus_areas

    if update:
        await profiles_col().update_one(
            {"user_id": user_id},
            {"$set": update},
        )
        logger.info(
            "Directly applied %d proposals to L1 for user_id=%s (skip_review=true)",
            len(proposals),
            user_id,
        )


async def process_document_upload(
    job_id: str,
    user_id: str,
    file_paths: list[str],
    mime_types: list[str],
    skip_review: bool,
) -> None:
    """Background task: extract documents, synthesize L1 facts, create proposals.

    Orchestrates the pipeline stages:
    1. Update job status to 'extracting'
    2. Extract text from each file independently (partial failures allowed)
    3. Update per-file statuses on the job record
    4. If any files succeeded, combine extracted text and update status to 'synthesizing'
    5. Send combined text to LLM for L1 fact synthesis
    6. On success: update job status to 'done' with proposals
    7. On failure: update job status to 'failed' with error; preserve extracted_text

    If ALL files fail extraction, marks job 'failed' immediately without synthesis.

    Args:
        job_id: The Upload_Job ID.
        user_id: The authenticated user's ID.
        file_paths: List of local file paths for uploaded files.
        mime_types: List of MIME types corresponding to each file.
        skip_review: If True, write proposals directly to L1 without confirmation.
    """
    try:
        # --- Stage 1: Extracting ---
        await _update_job_status(job_id, "extracting")

        # Process each file independently (Requirement 3.11, 9.4)
        extracted_texts: list[str] = []

        for i, (filepath, mime_type) in enumerate(zip(file_paths, mime_types)):
            try:
                result = await extract_document(filepath, mime_type)

                if result.success and result.text:
                    extracted_texts.append(result.text)
                    await _update_file_status(job_id, i, "extracted")
                else:
                    # Extraction returned a failure result
                    error_msg = result.error or "no extractable content"
                    await _update_file_status(job_id, i, "failed", error=error_msg)
                    logger.warning(
                        "File extraction failed for job %s, file index %d: %s",
                        job_id,
                        i,
                        error_msg,
                    )
            except Exception as e:
                # Catch unexpected errors so one file doesn't crash the entire batch
                error_msg = f"unexpected extraction error: {e}"
                await _update_file_status(job_id, i, "failed", error=error_msg)
                logger.error(
                    "Unexpected error extracting file index %d for job %s: %s",
                    i,
                    job_id,
                    e,
                )

        # If ALL files failed extraction, mark job as failed immediately
        if not extracted_texts:
            await _update_job_status(
                job_id,
                "failed",
                extra_fields={
                    "proposals": None,
                    "proposal_count": 0,
                },
            )
            logger.info(
                "All files failed extraction for job %s — marking as failed", job_id
            )
            return

        # --- Stage 2: Synthesizing ---
        # Combine extracted text from successful files (Requirement 4.4)
        combined_text = "\n\n---\n\n".join(extracted_texts)

        # Preserve extracted_text on the job record for retry (Requirement 9.5)
        await _update_job_status(
            job_id,
            "synthesizing",
            extra_fields={"extracted_text": combined_text},
        )

        # Call LLM synthesis (Requirement 4.1)
        synthesis_result = await synthesize_l1_facts(
            extracted_text=combined_text,
            user_id=user_id,
            job_id=job_id,
        )

        # --- Stage 3: Handle synthesis result ---
        if not synthesis_result.success:
            # Synthesis failed — mark job as failed, preserve extracted_text
            await _update_job_status(
                job_id,
                "failed",
                extra_fields={
                    "proposals": None,
                    "proposal_count": 0,
                },
            )
            logger.error(
                "Synthesis failed for job %s: %s", job_id, synthesis_result.error
            )
            return

        # Synthesis succeeded
        proposals = synthesis_result.proposals or []

        # --- Stage 4: Create pending changes or apply directly ---
        if proposals:
            if skip_review:
                # Write proposals directly to L1 memory (Requirement 5.7)
                await _apply_proposals_directly(user_id, proposals)
            else:
                # Create PendingProfileChange entries (Requirement 5.1, 5.4)
                await _create_pending_changes(user_id, job_id, proposals)

        # Store proposals on the job record and update proposal_count (Requirement 5.8)
        await _update_job_status(
            job_id,
            "done",
            extra_fields={
                "proposals": proposals,
                "proposal_count": len(proposals),
            },
        )

        logger.info(
            "Pipeline completed for job %s: %d proposals generated (skip_review=%s)",
            job_id,
            len(proposals),
            skip_review,
        )

    except Exception as e:
        # Catch-all: ensure the job doesn't stay in a non-terminal state
        logger.error(
            "Unhandled error in pipeline for job %s: %s", job_id, e, exc_info=True
        )
        try:
            await _update_job_status(
                job_id,
                "failed",
                extra_fields={
                    "proposals": None,
                    "proposal_count": 0,
                },
            )
        except Exception as update_err:
            logger.error(
                "Failed to update job %s status to failed: %s", job_id, update_err
            )
