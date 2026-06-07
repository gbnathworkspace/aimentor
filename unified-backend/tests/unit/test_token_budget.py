"""Unit tests for app/services/token_budget.py.

Faithful port of the Next.js `token-budget.ts`. Priority order:
Core Profile > Skill Graph > ImmediateContext > Episodic RAG.
Core context is never dropped; ImmediateContext is dropped oldest-first.
"""

import os
from unittest.mock import patch

import pytest

from app.services.token_budget import (
    DEFAULT_TOKEN_BUDGET,
    ImmediateContextDoc,
    apply_token_budget_priority,
    count_tokens,
    get_token_budget,
)


def _doc(job_id: str, token_count: int) -> ImmediateContextDoc:
    return ImmediateContextDoc(job_id=job_id, token_count=token_count)


class TestCountTokens:
    def test_empty_string_is_zero(self):
        assert count_tokens("") == 0

    def test_nonempty_is_positive(self):
        assert count_tokens("hello world") > 0


class TestGetTokenBudget:
    def test_default_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_token_budget() == DEFAULT_TOKEN_BUDGET

    def test_env_override(self):
        with patch.dict(os.environ, {"CONTEXT_TOKEN_BUDGET": "5000"}, clear=True):
            assert get_token_budget() == 5000

    def test_invalid_env_falls_back_to_default(self):
        with patch.dict(os.environ, {"CONTEXT_TOKEN_BUDGET": "notanumber"}, clear=True):
            assert get_token_budget() == DEFAULT_TOKEN_BUDGET


class TestApplyTokenBudgetPriority:
    def test_empty_docs(self):
        r = apply_token_budget_priority([], core_context_tokens=100, episodic_rag_tokens=50)
        assert r.included_docs == []
        assert r.dropped_docs == []
        assert r.included_tokens == 0
        assert r.budget_exceeded is False

    def test_everything_fits(self):
        docs = [_doc("a", 100), _doc("b", 200)]
        r = apply_token_budget_priority(
            docs, core_context_tokens=100, episodic_rag_tokens=50, token_budget=1000
        )
        assert [d.job_id for d in r.included_docs] == ["a", "b"]
        assert r.dropped_docs == []
        assert r.included_tokens == 300
        assert r.budget_exceeded is False

    def test_core_alone_exceeds_drops_all_immediate(self):
        docs = [_doc("a", 100), _doc("b", 100)]
        # core + episodic already over budget → no room for immediate
        r = apply_token_budget_priority(
            docs, core_context_tokens=900, episodic_rag_tokens=200, token_budget=1000
        )
        assert r.included_docs == []
        assert {d.job_id for d in r.dropped_docs} == {"a", "b"}
        assert r.included_tokens == 0
        assert r.budget_exceeded is True

    def test_drops_oldest_first_keeps_newest(self):
        # docs sorted oldest→newest: a(oldest), b, c(newest)
        docs = [_doc("a", 300), _doc("b", 300), _doc("c", 300)]
        # base = 200, budget = 800 → available for immediate = 600 → fits 2 newest (b,c=600)
        r = apply_token_budget_priority(
            docs, core_context_tokens=200, episodic_rag_tokens=0, token_budget=800
        )
        assert [d.job_id for d in r.included_docs] == ["b", "c"]  # chronological order
        assert [d.job_id for d in r.dropped_docs] == ["a"]  # oldest dropped
        assert r.included_tokens == 600
        assert r.budget_exceeded is True

    def test_total_never_exceeds_budget_when_exceeded(self):
        docs = [_doc("a", 500), _doc("b", 500), _doc("c", 500)]
        budget = 1000
        base = 200
        r = apply_token_budget_priority(
            docs, core_context_tokens=base, episodic_rag_tokens=0, token_budget=budget
        )
        assert base + r.included_tokens <= budget
        assert r.budget_exceeded is True

    def test_included_preserves_chronological_order(self):
        docs = [_doc("a", 100), _doc("b", 100), _doc("c", 100), _doc("d", 100)]
        r = apply_token_budget_priority(
            docs, core_context_tokens=100, episodic_rag_tokens=0, token_budget=350
        )
        # available = 250 → keep 2 newest (c,d) in order
        ids = [d.job_id for d in r.included_docs]
        assert ids == sorted(ids, key=lambda x: ["a", "b", "c", "d"].index(x))
