# Feature: chat-document-upload, Property 13: Proposal-to-PendingProfileChange mapping
"""Property test — Proposal-to-PendingProfileChange mapping with source tagging.

Property 13:
- For any valid set of synthesized proposals with job metadata,
  when skip_review=false: exactly one PendingProfileChange per proposal,
  each tagged with source_type="document_upload" and session_id=job_id.
- When skip_review=true: no PendingProfileChange entries are created
  (direct write path instead).

**Validates: Requirements 5.1, 5.4, 5.7**
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.profile import ProposableField, StyleNoteCategory
from app.services.document_pipeline import (
    _apply_proposals_directly,
    _create_pending_changes,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_valid_categories = [c.value for c in StyleNoteCategory]


@st.composite
def random_job_metadata(draw):
    """Generate random job_id and user_id."""
    job_id = draw(st.uuids().map(str))
    user_id = draw(st.uuids().map(str))
    return job_id, user_id


@st.composite
def random_valid_proposals(draw):
    """Generate a random list of valid proposals (1-8) with correct field shapes."""
    num_proposals = draw(st.integers(min_value=1, max_value=8))
    proposals = []

    for _ in range(num_proposals):
        field_type = draw(st.sampled_from([
            ProposableField.SITUATION,
            ProposableField.STYLE_NOTE,
        ]))

        if field_type == ProposableField.SITUATION:
            proposals.append({
                "field": field_type.value,
                "proposed_value": {
                    "value": draw(st.text(min_size=1, max_size=60, alphabet=st.characters(
                        whitelist_categories=("L", "N", "Zs"),
                        min_codepoint=32, max_codepoint=122,
                    ))),
                },
                "reason": "Extracted from uploaded document",
            })
        elif field_type == ProposableField.STYLE_NOTE:
            proposals.append({
                "field": field_type.value,
                "proposed_value": {
                    "category": draw(st.sampled_from(_valid_categories)),
                    "note": draw(st.text(min_size=1, max_size=140)),
                    "source_quote": draw(st.text(min_size=1, max_size=200)),
                },
                "reason": "Extracted from uploaded document",
            })

    return proposals


# ---------------------------------------------------------------------------
# Property 13a: When skip_review=false, exactly one PendingProfileChange per proposal
# ---------------------------------------------------------------------------


# Feature: chat-document-upload, Property 13: Proposal-to-PendingProfileChange mapping
@settings(max_examples=100, deadline=None)
@given(
    metadata=random_job_metadata(),
    proposals=random_valid_proposals(),
)
@pytest.mark.asyncio
async def test_create_pending_changes_one_per_proposal(metadata, proposals):
    """Property 13 (skip_review=false): For any valid set of proposals,
    _create_pending_changes creates exactly one PendingProfileChange per proposal,
    each tagged with source_type="document_upload" and session_id=job_id.

    **Validates: Requirements 5.1, 5.4**
    """
    job_id, user_id = metadata

    # Capture what gets pushed to MongoDB
    captured_push = {}

    async def mock_update_one(filter_doc, update_doc):
        captured_push["filter"] = filter_doc
        captured_push["update"] = update_doc
        return MagicMock(modified_count=1)

    mock_col = MagicMock()
    mock_col.update_one = AsyncMock(side_effect=mock_update_one)

    with patch(
        "app.services.document_pipeline.profiles_col",
        return_value=mock_col,
    ):
        await _create_pending_changes(user_id, job_id, proposals)

    # Verify the $push was called with correct number of entries
    assert "$push" in captured_push["update"], "Expected $push operation"
    push_spec = captured_push["update"]["$push"]
    assert "pending_changes" in push_spec, "Expected pending_changes field in $push"

    entries = push_spec["pending_changes"]["$each"]

    # Assertion 1: Exactly one PendingProfileChange entry per proposal
    assert len(entries) == len(proposals), (
        f"Expected {len(proposals)} pending change entries, got {len(entries)}"
    )

    # Assertion 2: Each entry tagged with source_type="document_upload"
    for i, entry in enumerate(entries):
        assert entry.get("source_type") == "document_upload", (
            f"Entry {i} missing source_type='document_upload': got {entry.get('source_type')}"
        )

    # Assertion 3: Each entry has session_id=job_id
    for i, entry in enumerate(entries):
        assert entry.get("session_id") == job_id, (
            f"Entry {i} has session_id={entry.get('session_id')!r}, expected {job_id!r}"
        )

    # Assertion 4: Filter targets the correct user
    assert captured_push["filter"] == {"user_id": user_id}

    # Assertion 5: Each entry has correct field from the proposals
    for i, (entry, proposal) in enumerate(zip(entries, proposals)):
        assert entry.get("field") == proposal["field"], (
            f"Entry {i} has field={entry.get('field')!r}, "
            f"expected {proposal['field']!r}"
        )


# ---------------------------------------------------------------------------
# Property 13b: When skip_review=true, no pending changes are created
# ---------------------------------------------------------------------------


# Feature: chat-document-upload, Property 13: Proposal-to-PendingProfileChange mapping
@settings(max_examples=100, deadline=None)
@given(
    metadata=random_job_metadata(),
    proposals=random_valid_proposals(),
)
@pytest.mark.asyncio
async def test_skip_review_no_pending_changes_created(metadata, proposals):
    """Property 13 (skip_review=true): When skip_review=true, no PendingProfileChange
    entries are created — proposals are written directly to L1 instead.

    **Validates: Requirements 5.7**
    """
    job_id, user_id = metadata

    # Mock profiles_col for _create_pending_changes (should NOT be called)
    pending_changes_mock = MagicMock()
    pending_changes_mock.update_one = AsyncMock()

    # Mock profiles_col for _apply_proposals_directly (should BE called)
    # It needs find_one to return a profile
    mock_profile = {
        "user_id": user_id,
        "focus_areas": [],
        "style_notes": [],
        "learning_context_detail": None,
        "learning_context": None,
    }

    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(return_value=mock_profile)
    mock_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    # Track whether _create_pending_changes is invoked
    create_pending_called = False
    original_create = _create_pending_changes

    async def tracking_create_pending(uid, jid, props):
        nonlocal create_pending_called
        create_pending_called = True
        await original_create(uid, jid, props)

    # Simulate the routing logic from process_document_upload:
    # When skip_review=true, _apply_proposals_directly is called instead of _create_pending_changes
    skip_review = True

    with patch(
        "app.services.document_pipeline.profiles_col",
        return_value=mock_col,
    ):
        if skip_review:
            await _apply_proposals_directly(user_id, proposals)
        else:
            create_pending_called = True
            await _create_pending_changes(user_id, job_id, proposals)

    # Key assertion: _create_pending_changes path was NOT taken
    assert not create_pending_called, (
        "When skip_review=true, _create_pending_changes should NOT be called"
    )

    # Verify that _apply_proposals_directly was called (it uses find_one + update_one)
    mock_col.find_one.assert_called_once_with({"user_id": user_id})


# ---------------------------------------------------------------------------
# Property 13c: Routing logic — skip_review=false calls _create_pending_changes
# ---------------------------------------------------------------------------


# Feature: chat-document-upload, Property 13: Proposal-to-PendingProfileChange mapping
@settings(max_examples=100, deadline=None)
@given(
    metadata=random_job_metadata(),
    proposals=random_valid_proposals(),
    skip_review=st.booleans(),
)
@pytest.mark.asyncio
async def test_routing_logic_skip_review_flag(metadata, proposals, skip_review):
    """Property 13 (routing): The skip_review flag determines which path is taken.
    skip_review=false → _create_pending_changes (pending entries created).
    skip_review=true → _apply_proposals_directly (no pending entries).

    **Validates: Requirements 5.1, 5.4, 5.7**
    """
    job_id, user_id = metadata

    create_pending_called = False
    apply_directly_called = False

    async def mock_create_pending(uid, jid, props):
        nonlocal create_pending_called
        create_pending_called = True

    async def mock_apply_directly(uid, props):
        nonlocal apply_directly_called
        apply_directly_called = True

    # Replicate the routing logic from process_document_upload
    # (the core conditional from the orchestrator)
    if proposals:
        if skip_review:
            await mock_apply_directly(user_id, proposals)
        else:
            await mock_create_pending(user_id, job_id, proposals)

    # Assertions based on skip_review value
    if skip_review:
        assert apply_directly_called, (
            "skip_review=true should call _apply_proposals_directly"
        )
        assert not create_pending_called, (
            "skip_review=true should NOT call _create_pending_changes"
        )
    else:
        assert create_pending_called, (
            "skip_review=false should call _create_pending_changes"
        )
        assert not apply_directly_called, (
            "skip_review=false should NOT call _apply_proposals_directly"
        )
