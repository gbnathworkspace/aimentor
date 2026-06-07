"""Token budget priority — Python port of the Next.js `token-budget.ts`.

Ensures the assembled context fits within the configured token budget.
Priority order: Core Profile > Skill Graph > ImmediateContext > Episodic RAG.

When the combined context exceeds budget:
1. Core Profile and Skill Graph are NEVER dropped.
2. ImmediateContext blocks are dropped oldest-first.
3. The final assembled context fits within the configured token budget.

Uses the cl100k_base encoding (same family js-tiktoken's `gpt-4` model uses)
so token counts match the TypeScript implementation.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

# Conservative default; leaves room for the conversation window + LLM response.
DEFAULT_TOKEN_BUDGET = 16_000

_ENCODING_NAME = "cl100k_base"  # js-tiktoken's 'gpt-4' uses this encoding


@lru_cache(maxsize=1)
def _encoding() -> "tiktoken.Encoding":
    return tiktoken.get_encoding(_ENCODING_NAME)


def get_token_budget() -> int:
    """Return the configured token budget from CONTEXT_TOKEN_BUDGET or the default."""
    env_budget = os.environ.get("CONTEXT_TOKEN_BUDGET")
    if env_budget:
        try:
            parsed = int(env_budget)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_TOKEN_BUDGET


def count_tokens(text: str) -> int:
    """Count tokens in a string using the cl100k_base tokenizer."""
    if not text:
        return 0
    return len(_encoding().encode(text))


@dataclass
class ImmediateContextDoc:
    """An ImmediateContext block. Only job_id + token_count drive the algorithm."""

    job_id: str
    token_count: int


@dataclass
class BudgetPriorityResult:
    included_docs: list[ImmediateContextDoc] = field(default_factory=list)
    dropped_docs: list[ImmediateContextDoc] = field(default_factory=list)
    included_tokens: int = 0
    budget_exceeded: bool = False


def apply_token_budget_priority(
    docs: list[ImmediateContextDoc],
    core_context_tokens: int,
    episodic_rag_tokens: int,
    token_budget: int | None = None,
) -> BudgetPriorityResult:
    """Decide which ImmediateContext docs fit within the token budget.

    Args:
        docs: ImmediateContext docs sorted by created-at ascending (oldest first).
        core_context_tokens: Tokens for Core Profile + Skill Graph — never dropped.
        episodic_rag_tokens: Tokens for Episodic RAG results — part of the base.
        token_budget: Max total tokens (defaults to the configured budget).
    """
    budget = token_budget if token_budget is not None else get_token_budget()

    if not docs:
        return BudgetPriorityResult()

    base_tokens = core_context_tokens + episodic_rag_tokens
    total_immediate_tokens = sum(d.token_count for d in docs)

    # Everything fits.
    if base_tokens + total_immediate_tokens <= budget:
        return BudgetPriorityResult(
            included_docs=list(docs),
            dropped_docs=[],
            included_tokens=total_immediate_tokens,
            budget_exceeded=False,
        )

    # Budget exceeded — room left for ImmediateContext after the base.
    available_for_immediate = max(0, budget - base_tokens)

    if available_for_immediate <= 0:
        return BudgetPriorityResult(
            included_docs=[],
            dropped_docs=list(docs),
            included_tokens=0,
            budget_exceeded=True,
        )

    # Greedily include newest→oldest (drop oldest first), keep chronological order.
    included: list[ImmediateContextDoc] = []
    used_tokens = 0
    for doc in reversed(docs):
        if used_tokens + doc.token_count <= available_for_immediate:
            included.insert(0, doc)  # maintain chronological order
            used_tokens += doc.token_count

    included_ids = {d.job_id for d in included}
    dropped = [d for d in docs if d.job_id not in included_ids]

    return BudgetPriorityResult(
        included_docs=included,
        dropped_docs=dropped,
        included_tokens=used_tokens,
        budget_exceeded=True,
    )
