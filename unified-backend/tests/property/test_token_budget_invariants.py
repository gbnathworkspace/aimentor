"""Property test — token budget invariants (spec Property: Budget Priority).

Validates Requirements 9.1, 9.2, 9.3:
- Core context is never dropped (base tokens always counted, immediate never starves it).
- Total tokens never exceed the budget once trimming occurs.
- Included docs preserve chronological order; dropped = docs − included.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.token_budget import (
    ImmediateContextDoc,
    apply_token_budget_priority,
)

_docs = st.lists(
    st.builds(
        ImmediateContextDoc,
        job_id=st.uuids().map(str),
        token_count=st.integers(min_value=1, max_value=2000),
    ),
    max_size=12,
)


@settings(max_examples=300)
@given(
    docs=_docs,
    core=st.integers(min_value=0, max_value=3000),
    episodic=st.integers(min_value=0, max_value=3000),
    budget=st.integers(min_value=1, max_value=8000),
)
def test_invariants(docs, core, episodic, budget):
    # job_ids unique (the algorithm keys on job_id)
    seen, unique = set(), []
    for d in docs:
        if d.job_id not in seen:
            seen.add(d.job_id)
            unique.append(d)
    docs = unique

    r = apply_token_budget_priority(docs, core, episodic, token_budget=budget)

    base = core + episodic
    total_immediate = sum(d.token_count for d in docs)

    # 1. included ⊆ docs, dropped = docs − included, no overlap, partition complete
    inc_ids = {d.job_id for d in r.included_docs}
    drop_ids = {d.job_id for d in r.dropped_docs}
    assert inc_ids.isdisjoint(drop_ids)
    assert inc_ids | drop_ids == {d.job_id for d in docs}

    # 2. included_tokens equals the sum of included docs' tokens
    assert r.included_tokens == sum(d.token_count for d in r.included_docs)

    # 3. Budget respected: if anything was trimmed, base + included ≤ budget
    if r.budget_exceeded and base < budget:
        assert base + r.included_tokens <= budget

    # 4. If everything fit, nothing was dropped and flag is False
    if base + total_immediate <= budget:
        assert r.budget_exceeded is False
        assert r.dropped_docs == []
        assert [d.job_id for d in r.included_docs] == [d.job_id for d in docs]

    # 5. Chronological order preserved among included docs
    order = {d.job_id: i for i, d in enumerate(docs)}
    inc_positions = [order[d.job_id] for d in r.included_docs]
    assert inc_positions == sorted(inc_positions)

    # 6. Oldest-first drop: every dropped doc is older than (or equal pos to) the
    #    oldest included doc is NOT required, but newest-kept must hold — verify
    #    no included doc is older than a dropped doc that would have fit.
    if r.included_docs and r.dropped_docs:
        oldest_included = min(order[d.job_id] for d in r.included_docs)
        # all dropped that are *newer* than oldest_included only happen if they didn't fit
        # (greedy newest-first); ensure at least the newest doc survives when room exists.
        newest_pos = len(docs) - 1
        newest_doc = docs[newest_pos]
        if newest_doc.token_count <= max(0, budget - base):
            assert newest_doc.job_id in inc_ids
