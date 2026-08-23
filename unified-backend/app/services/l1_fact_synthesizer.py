"""LLM-powered L1 fact synthesis for the chat document upload pipeline.

Takes extracted document text and produces structured field proposals
conforming to the L1 memory schema (style_notes, situations). Validates
proposals against schema constraints and handles LLM errors with retry logic.

This module is part of the Document Ingestion Pipeline and does NOT
interact with Vector DB, Skill Graph, or the existing IngestionService.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic
import tiktoken

from app.config.database import profiles_col
from app.config.settings import get_settings
from app.models.document_upload import L1SynthesisOutput, SynthesizedStyleNote
from app.models.profile import ProposableField, StyleNoteCategory

logger = logging.getLogger(__name__)

_ENCODING_NAME = "cl100k_base"
_MAX_TOKENS = 8000
_LLM_MODEL = "claude-haiku-4-5-20251001"
_LLM_TIMEOUT_SECONDS = 30
_LLM_RETRY_DELAY_SECONDS = 2

# Maximum number of style notes allowed per user profile.
MAX_STYLE_NOTES = 5

# Sentence-ending pattern: period, question mark, or exclamation mark
# followed by whitespace or end-of-string.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s|$)")

_SYSTEM_PROMPT = """\
You are an expert learning profile analyst. You receive extracted text from documents \
a user has uploaded (resumes, job descriptions, syllabi, notes, etc.). Your task is to \
analyze the text and produce structured L1 memory field proposals.

Produce a JSON object with the following optional fields (include ONLY when the text \
contains clear, relevant evidence):

{
  "style_notes": [
    {
      "category": one of "pacing", "communication", "motivation", "misconception", "context",
      "note": "concise observation about the learner (max 140 chars)",
      "source_quote": "verbatim text from the document supporting this (max 200 chars)"
    }
  ],
  "situations": ["short phrase describing a fact/situation about the learner (max 60 chars each)"]
}

Rules:
- Only propose fields when you have CLEAR evidence in the text. Do not guess or infer without support.
- Each style_note MUST include a source_quote that is a VERBATIM span from the input text (not paraphrased).
- source_quote must be at most 200 characters.
- Each situation must be at most 60 characters.
- note in style_notes must be at most 140 characters.
- Return ONLY valid JSON, no markdown formatting, no explanation outside the JSON.
- If nothing relevant is found, return an empty JSON object: {}
"""


def _get_encoding() -> tiktoken.Encoding:
    """Return the cl100k_base encoding for token counting."""
    return tiktoken.get_encoding(_ENCODING_NAME)


def truncate_to_token_limit(text: str, max_tokens: int = _MAX_TOKENS) -> str:
    """Truncate text to fit within max_tokens at a sentence boundary.

    Counts tokens using cl100k_base. If the text fits, returns it unchanged.
    Otherwise, finds the last sentence boundary within the token limit.

    Args:
        text: The input text to potentially truncate.
        max_tokens: Maximum number of tokens allowed.

    Returns:
        The text truncated at a sentence boundary, or the full text if it fits.
    """
    if not text:
        return text

    encoding = _get_encoding()
    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return text

    # Decode the truncated tokens back to text
    truncated_text = encoding.decode(tokens[:max_tokens])

    # Find the last sentence boundary in the truncated text
    last_boundary = -1
    for match in _SENTENCE_BOUNDARY_RE.finditer(truncated_text):
        last_boundary = match.end()

    if last_boundary > 0:
        return truncated_text[:last_boundary].rstrip()

    # No sentence boundary found — return what we have
    return truncated_text.rstrip()


@dataclass
class SynthesisResult:
    """Result of the LLM fact synthesis step.

    Attributes:
        proposals: List of validated PendingProfileChange-shaped dicts.
        success: Whether synthesis completed successfully.
        error: Error message if synthesis failed, None otherwise.
    """

    proposals: list[dict] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


def _validate_style_notes(
    notes: list[dict],
) -> list[SynthesizedStyleNote]:
    """Validate style note entries from LLM output.

    Discards notes with invalid category, missing source_quote,
    source_quote > 200 chars, or note > 140 chars.

    Args:
        notes: Raw style note dicts from LLM.

    Returns:
        List of validated SynthesizedStyleNote instances.
    """
    validated = []
    for note_dict in notes:
        try:
            category_val = note_dict.get("category", "")
            # Validate category is a valid enum
            StyleNoteCategory(category_val)

            source_quote = note_dict.get("source_quote", "")
            note_text = note_dict.get("note", "")

            # Validate constraints
            if not source_quote or len(source_quote) > 200:
                logger.warning(
                    "Discarding style note: source_quote missing or > 200 chars"
                )
                continue
            if not note_text or len(note_text) > 140:
                logger.warning(
                    "Discarding style note: note missing or > 140 chars"
                )
                continue

            validated.append(
                SynthesizedStyleNote(
                    category=StyleNoteCategory(category_val),
                    note=note_text,
                    source_quote=source_quote,
                )
            )
        except (ValueError, KeyError) as e:
            logger.warning("Discarding invalid style note: %s", e)
            continue

    return validated


def _validate_situations(items: list[str]) -> list[str]:
    """Validate situation entries — each must be ≤ 60 characters.

    Args:
        items: Raw situation strings from LLM.

    Returns:
        List of valid situation strings (≤ 60 chars, non-empty).
    """
    return [s for s in items if s and len(s) <= 60]


def _build_proposals(
    synthesis_output: L1SynthesisOutput,
    job_id: str,
) -> list[dict]:
    """Build PendingProfileChange-shaped dicts from validated synthesis output.

    Args:
        synthesis_output: The validated L1SynthesisOutput.
        job_id: The Upload_Job ID for traceability.

    Returns:
        List of proposal dicts shaped like PendingProfileChange.
    """
    proposals = []

    # Style notes proposals — one per note
    if synthesis_output.style_notes:
        raw_notes = [n.model_dump() for n in synthesis_output.style_notes]
        valid_notes = _validate_style_notes(raw_notes)
        for note in valid_notes:
            proposals.append({
                "field": ProposableField.STYLE_NOTE.value,
                "proposed_value": {
                    "category": note.category.value,
                    "note": note.note,
                    "source_quote": note.source_quote,
                },
                "reason": f"Style insight from uploaded document",
            })

    # Situation proposals — one per fact
    if synthesis_output.situations:
        valid_situations = _validate_situations(synthesis_output.situations)
        for situation in valid_situations:
            proposals.append({
                "field": ProposableField.SITUATION.value,
                "proposed_value": {"value": situation},
                "reason": "Fact identified from uploaded document",
            })

    return proposals


async def _get_user_profile_state(user_id: str) -> dict:
    """Fetch the user's current situations and style_notes from their profile.

    Used by the accumulation logic to deduplicate situations and detect
    style note cap conditions.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        Dict with 'situations' (list[str]) and 'style_notes' (list[dict]).
        Returns empty lists if the profile doesn't exist.
    """
    profile = await profiles_col().find_one(
        {"user_id": user_id},
        {"learning_context_detail": 1, "style_notes": 1},
    )
    if not profile:
        return {"situations": [], "style_notes": []}
    return {
        "situations": (profile.get("learning_context_detail") or {}).get("situations") or [],
        "style_notes": profile.get("style_notes") or [],
    }


def deduplicate_situations(
    proposed: list[str],
    existing: list[str],
) -> list[str]:
    """Remove proposed situations that are case-insensitive duplicates of existing ones.

    Compares each proposed situation against all existing situations using
    case-insensitive exact string matching. Only situations with no match
    in the existing list are returned.

    Args:
        proposed: List of proposed situation strings from LLM.
        existing: List of existing situation strings from user's profile.

    Returns:
        List of proposed situations that are NOT duplicates of existing ones.
    """
    existing_lower = {s.lower() for s in existing}
    return [s for s in proposed if s.lower() not in existing_lower]


def flag_style_notes_at_cap(
    proposals: list[dict],
    existing_style_notes_count: int,
) -> list[dict]:
    """Flag style note proposals when the user has reached the maximum (5).

    When a user already has MAX_STYLE_NOTES style notes, proposed style notes
    are flagged with `requires_replacement=True` so the frontend can show the
    replacement flow (user must dismiss the proposal or select an existing note
    to replace).

    Proposals are NEVER silently overwritten or discarded — they are always
    presented to the user for decision.

    Args:
        proposals: List of proposal dicts from _build_proposals.
        existing_style_notes_count: Number of style notes currently on the user's profile.

    Returns:
        The same list of proposals, with style_note proposals annotated with
        `requires_replacement=True` when the cap is reached.
    """
    flagged = []
    for proposal in proposals:
        if (
            proposal["field"] == ProposableField.STYLE_NOTE.value
            and existing_style_notes_count >= MAX_STYLE_NOTES
        ):
            # Flag this proposal so the frontend knows to show the replacement flow.
            flagged.append({
                **proposal,
                "requires_replacement": True,
            })
        else:
            flagged.append(proposal)
    return flagged


async def accumulate_proposals(
    proposals: list[dict],
    user_id: str,
) -> list[dict]:
    """Apply accumulation logic: deduplicate situations and flag style notes at cap.

    This function ensures that:
    - Proposed situations that are case-insensitive duplicates of existing ones
      are discarded (Requirement 7.2).
    - When the user already has 5 style notes, new style_note proposals are
      flagged with `requires_replacement=True` for the replacement flow
      (Requirement 7.3, 7.4).
    - Proposals are purely additive — no existing L1 values are removed or
      overwritten (Requirement 7.1).

    Args:
        proposals: Raw proposals from _build_proposals.
        user_id: The authenticated user's ID.

    Returns:
        Accumulated proposals with duplicates removed and flags applied.
    """
    if not proposals:
        return proposals

    # Fetch current profile state
    profile_state = await _get_user_profile_state(user_id)
    existing_situations = profile_state["situations"]
    existing_style_notes = profile_state["style_notes"]
    existing_style_notes_count = len(existing_style_notes)

    # Step 1: Deduplicate situation proposals against existing situations
    accumulated = []
    for proposal in proposals:
        if proposal["field"] == ProposableField.SITUATION.value:
            proposed_situation = proposal["proposed_value"].get("value", "")
            # Only keep if not a case-insensitive duplicate
            deduped = deduplicate_situations([proposed_situation], existing_situations)
            if deduped:
                accumulated.append(proposal)
            else:
                logger.info(
                    "Discarding duplicate situation proposal: %r (already exists)",
                    proposed_situation,
                )
        else:
            accumulated.append(proposal)

    # Step 2: Flag style note proposals when cap is reached
    accumulated = flag_style_notes_at_cap(accumulated, existing_style_notes_count)

    return accumulated


async def synthesize_l1_facts(
    extracted_text: str,
    user_id: str,
    job_id: str,
) -> SynthesisResult:
    """Send extracted text to LLM and produce structured L1 field proposals.

    Truncates combined text to fit within 8000 tokens at sentence boundary,
    sends to LLM with a system prompt, parses and validates the response
    against L1 schema constraints.

    Args:
        extracted_text: Combined text from all successfully extracted files.
        user_id: The user's ID, for traceability.
        job_id: The Upload_Job ID for traceability.

    Returns:
        SynthesisResult with validated proposals or error details.
    """
    if not extracted_text or not extracted_text.strip():
        return SynthesisResult(
            proposals=[],
            success=True,
            error=None,
        )

    # Step 1: Truncate to token limit at sentence boundary
    truncated_text = truncate_to_token_limit(extracted_text, _MAX_TOKENS)

    # Step 2: Call LLM with retry logic
    # On failure (timeout, rate limit, service error), retry once after 2-second delay.
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    llm_messages = [
        {
            "role": "user",
            "content": (
                "Analyze the following extracted document text and produce "
                "structured L1 memory field proposals:\n\n"
                f"---\n{truncated_text}\n---"
            ),
        }
    ]

    response = None
    last_error: Optional[Exception] = None

    for attempt in range(2):  # attempt 0 = first try, attempt 1 = retry
        try:
            response = await client.messages.create(
                model=_LLM_MODEL,
                max_tokens=2000,
                system=_SYSTEM_PROMPT,
                messages=llm_messages,
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            last_error = None
            break  # Success — no need to retry
        except Exception as e:
            last_error = e
            if attempt == 0:
                # First failure — log and retry after delay
                logger.warning(
                    "LLM call failed for job %s (attempt 1), retrying after %ds: %s",
                    job_id,
                    _LLM_RETRY_DELAY_SECONDS,
                    e,
                )
                await asyncio.sleep(_LLM_RETRY_DELAY_SECONDS)
            else:
                # Retry also failed
                logger.error(
                    "LLM call failed for job %s (attempt 2, retry exhausted): %s",
                    job_id,
                    e,
                )

    if last_error is not None:
        return SynthesisResult(
            proposals=[],
            success=False,
            error=f"LLM call failed after retry: {type(last_error).__name__}: {last_error}",
        )

    # Step 3: Extract text from response
    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    response_text = response_text.strip()

    if not response_text:
        return SynthesisResult(
            proposals=[],
            success=True,
            error=None,
        )

    # Step 4: Parse JSON response
    try:
        # Handle potential markdown code fences
        if response_text.startswith("```"):
            # Strip code fence
            lines = response_text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            response_text = "\n".join(lines)

        parsed = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(
            "LLM response is not valid JSON for job %s — discarding proposals, "
            "marking job failed: %s",
            job_id,
            e,
        )
        return SynthesisResult(
            proposals=[],
            success=False,
            error=f"LLM response is not valid JSON: {e}",
        )

    # Step 5: Empty response means no proposals
    if not parsed or parsed == {}:
        return SynthesisResult(proposals=[], success=True, error=None)

    # Step 6: Parse into L1SynthesisOutput with validation
    try:
        synthesis_output = L1SynthesisOutput.model_validate(parsed)
    except Exception as e:
        logger.error(
            "LLM response doesn't conform to L1SynthesisOutput schema for job %s — "
            "discarding proposals, marking job failed: %s",
            job_id,
            e,
        )
        return SynthesisResult(
            proposals=[],
            success=False,
            error=f"LLM response doesn't conform to schema: {e}",
        )

    # Step 7: Build validated proposals
    proposals = _build_proposals(synthesis_output, job_id)

    # Step 8: Accumulation — deduplicate situations and flag style notes at cap
    proposals = await accumulate_proposals(proposals, user_id)

    return SynthesisResult(
        proposals=proposals,
        success=True,
        error=None,
    )
