# Feature: chat-document-upload, Properties 14, 15
"""Property tests for accumulation invariant and focus area deduplication.

Property 14: Accumulation invariant — no existing values lost
Property 15: Focus area case-insensitive deduplication

**Validates: Requirements 7.1, 7.2**
"""

from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.profile import ProposableField, StyleNoteCategory
from app.services.l1_fact_synthesizer import (
    accumulate_proposals,
    deduplicate_situations,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generates random focus area strings (1-60 chars)
_focus_area_strategy = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), min_codepoint=32, max_codepoint=122),
)


@st.composite
def random_existing_profile(draw):
    """Generate a random existing profile state with focus_areas and style_notes."""
    num_situations = draw(st.integers(min_value=0, max_value=10))
    situations = draw(
        st.lists(
            _focus_area_strategy,
            min_size=num_situations,
            max_size=num_situations,
        )
    )

    num_style_notes = draw(st.integers(min_value=0, max_value=5))
    style_notes = [
        {"category": "pacing", "note": f"note {i}", "session_id": f"s{i}"}
        for i in range(num_style_notes)
    ]

    return {"situations": situations, "style_notes": style_notes}


_valid_categories = [c.value for c in StyleNoteCategory]


@st.composite
def random_proposals(draw):
    """Generate a random list of proposals (mixed field types)."""
    num_proposals = draw(st.integers(min_value=1, max_value=8))
    proposals = []

    for _ in range(num_proposals):
        field_type = draw(st.sampled_from([
            ProposableField.SITUATION,
            ProposableField.STYLE_NOTE,
        ]))

        if field_type == ProposableField.SITUATION:
            value = draw(_focus_area_strategy)
            proposals.append({
                "field": field_type.value,
                "proposed_value": {"value": value},
                "reason": "From document",
            })
        elif field_type == ProposableField.STYLE_NOTE:
            proposals.append({
                "field": field_type.value,
                "proposed_value": {
                    "category": draw(st.sampled_from(_valid_categories)),
                    "note": draw(st.text(min_size=1, max_size=50)),
                    "source_quote": draw(st.text(min_size=1, max_size=100)),
                },
                "reason": "From document",
            })

    return proposals


# ---------------------------------------------------------------------------
# Property 14: Accumulation invariant — no L1 values are overwritten or removed
# ---------------------------------------------------------------------------


# Feature: chat-document-upload, Property 14: Accumulation invariant
@settings(max_examples=100, deadline=None)
@given(
    existing_profile=random_existing_profile(),
    proposals=random_proposals(),
)
@pytest.mark.asyncio
async def test_accumulation_never_loses_existing_values(existing_profile, proposals):
    """Property 14: For any existing profile state and any set of proposals,
    accumulation never removes or overwrites existing values — only discards
    duplicate focus_area proposals or flags style notes at cap.

    **Validates: Requirements 7.1**
    """
    with patch(
        "app.services.l1_fact_synthesizer._get_user_profile_state",
        new_callable=AsyncMock,
        return_value=existing_profile,
    ):
        result = await accumulate_proposals(proposals, "test-user")

    # The result should only contain proposals from the input — no new ones invented
    # (accumulate_proposals filters/flags but never adds new proposals)
    assert len(result) <= len(proposals), (
        f"Result has {len(result)} proposals, but input only had {len(proposals)}. "
        f"Accumulation should never add proposals."
    )

    # Every proposal in the result must have come from the original proposals list
    for r_proposal in result:
        # Strip the requires_replacement flag for comparison
        base_proposal = {k: v for k, v in r_proposal.items() if k != "requires_replacement"}
        found = any(
            all(base_proposal.get(k) == p.get(k) for k in base_proposal)
            for p in proposals
        )
        assert found, (
            f"Result contains a proposal not in original input: {r_proposal}"
        )

    # Non-focus-area, non-style-note proposals are NEVER removed by accumulation
    non_focus_non_style = [
        p for p in proposals
        if p["field"] not in (
            ProposableField.SITUATION.value,
            ProposableField.STYLE_NOTE.value,
        )
    ]
    result_non_focus_non_style = [
        p for p in result
        if p["field"] not in (
            ProposableField.SITUATION.value,
            ProposableField.STYLE_NOTE.value,
        )
    ]
    assert len(result_non_focus_non_style) == len(non_focus_non_style), (
        f"Non-focus/style proposals were modified: "
        f"input had {len(non_focus_non_style)}, result has {len(result_non_focus_non_style)}"
    )

    # Focus area proposals that are NOT duplicates of existing must be kept
    existing_focus_lower = {a.lower() for a in existing_profile["situations"]}
    for proposal in proposals:
        if proposal["field"] == ProposableField.SITUATION.value:
            area = proposal["proposed_value"]["value"]
            if area.lower() not in existing_focus_lower:
                # This non-duplicate should be in the result
                assert any(
                    p["field"] == ProposableField.SITUATION.value
                    and p["proposed_value"]["value"] == area
                    for p in result
                ), (
                    f"Non-duplicate focus area {area!r} was incorrectly removed. "
                    f"Existing (lowered): {existing_focus_lower}"
                )

    # Style note proposals are NEVER removed — only flagged
    style_proposals_in = [
        p for p in proposals if p["field"] == ProposableField.STYLE_NOTE.value
    ]
    style_proposals_out = [
        p for p in result if p["field"] == ProposableField.STYLE_NOTE.value
    ]
    assert len(style_proposals_out) == len(style_proposals_in), (
        f"Style note proposals count changed: input {len(style_proposals_in)}, "
        f"output {len(style_proposals_out)}. Style notes should never be removed, "
        f"only flagged for replacement."
    )


# ---------------------------------------------------------------------------
# Property 15: Focus area case-insensitive deduplication
# ---------------------------------------------------------------------------

@st.composite
def strings_with_case_variations(draw):
    """Generate a list of strings where some may be case-variations of each other."""
    # Generate base strings
    num_bases = draw(st.integers(min_value=1, max_value=5))
    bases = draw(
        st.lists(
            st.text(min_size=1, max_size=40, alphabet="abcdefghijklmnopqrstuvwxyz "),
            min_size=num_bases,
            max_size=num_bases,
        )
    )

    # Create case variations: for each base, optionally include upper/title variants
    result = []
    for base in bases:
        result.append(base)
        if draw(st.booleans()):
            result.append(base.upper())
        if draw(st.booleans()):
            result.append(base.title())
        if draw(st.booleans()):
            result.append(base.swapcase())

    return result


@st.composite
def proposed_and_existing_focus_areas(draw):
    """Generate proposed and existing focus area lists with potential overlaps."""
    # Generate existing focus areas
    num_existing = draw(st.integers(min_value=0, max_value=8))
    existing = draw(
        st.lists(
            _focus_area_strategy,
            min_size=num_existing,
            max_size=num_existing,
        )
    )

    # Generate proposed focus areas — some may be case-variations of existing
    num_proposed = draw(st.integers(min_value=1, max_value=8))
    proposed = []

    for _ in range(num_proposed):
        if existing and draw(st.booleans()):
            # Create a case-variation of an existing area
            base = draw(st.sampled_from(existing))
            variation = draw(st.sampled_from([
                base.upper(),
                base.lower(),
                base.title(),
                base.swapcase(),
            ]))
            proposed.append(variation)
        else:
            # Generate a new unique area
            proposed.append(draw(_focus_area_strategy))

    return proposed, existing


# Feature: chat-document-upload, Property 15: Focus area deduplication
@settings(max_examples=100, deadline=None)
@given(data=proposed_and_existing_focus_areas())
def test_focus_area_deduplication_no_case_insensitive_duplicates(data):
    """Property 15: After deduplication, no proposed focus area matches an existing
    one under case-insensitive comparison.

    **Validates: Requirements 7.2**
    """
    proposed, existing = data

    result = deduplicate_situations(proposed, existing)

    existing_lower = {area.lower() for area in existing}

    # No result item should be a case-insensitive duplicate of any existing item
    for area in result:
        assert area.lower() not in existing_lower, (
            f"Deduplicated result contains {area!r} which is a case-insensitive "
            f"duplicate of an existing area. Existing (lowered): {existing_lower}"
        )

    # Every proposed item that is NOT a duplicate should be in the result
    for area in proposed:
        if area.lower() not in existing_lower:
            assert area in result, (
                f"Non-duplicate proposed area {area!r} was incorrectly removed. "
                f"Existing (lowered): {existing_lower}"
            )

    # Result should be a subset of proposed (no new items introduced)
    for area in result:
        assert area in proposed, (
            f"Result contains {area!r} which was not in the proposed list"
        )


# Feature: chat-document-upload, Property 15: Focus area deduplication (case variations)
@settings(max_examples=100, deadline=None)
@given(areas=strings_with_case_variations())
def test_focus_area_self_dedup_against_lowered_set(areas):
    """Property 15 (supplementary): When existing areas are the lowered versions of
    proposed areas, all case-insensitive matches are removed.

    **Validates: Requirements 7.2**
    """
    # Use the lowered set of all areas as "existing"
    existing = list({a.lower() for a in areas})
    proposed = areas

    result = deduplicate_situations(proposed, existing)

    # Every area in the result should NOT be a case-insensitive match of existing
    existing_lower = {e.lower() for e in existing}
    for area in result:
        assert area.lower() not in existing_lower, (
            f"Area {area!r} (lower: {area.lower()!r}) should have been removed "
            f"as it matches existing. Existing lower set: {existing_lower}"
        )
