"""Hand-labeled cases for the classify_relevance eval (see
.kiro/specs/topic-scoping/requirements.md's deferred Evals section, sourced
from the Topic Scoping design doc's own eval plan).

Each case is (topic, list, text, expected_relevant, category). `list` is
which of classify_relevance's two input lists `text` belongs to
("situations" or "contexts") — the function treats both identically, so
this only matters for exercising both code paths.

Scope note: the source doc asks for ~15-20 hand-labeled cases per category
(100-150 total), reviewed by a human. This set is deliberately smaller
(~3-4 per category) — a real reviewed set of this size is worth more than a
padded one nobody actually checked, and expanding it later is additive, not
a rewrite. Every category from the source doc is represented at least once.
"""

EVAL_CASES = [
    # --- clearly_relevant: sanity baseline ---
    {
        "topic": "React",
        "list": "situations",
        "text": "building a portfolio site in React",
        "expected_relevant": True,
        "category": "clearly_relevant",
    },
    {
        "topic": "Python",
        "list": "situations",
        "text": "writing a Python script to automate reports at work",
        "expected_relevant": True,
        "category": "clearly_relevant",
    },
    {
        "topic": "SQL",
        "list": "contexts",
        "text": "database administrator role, working with PostgreSQL daily",
        "expected_relevant": True,
        "category": "clearly_relevant",
    },
    {
        "topic": "Public Speaking",
        "list": "situations",
        "text": "giving a conference talk next month",
        "expected_relevant": True,
        "category": "clearly_relevant",
    },

    # --- clearly_irrelevant: sanity baseline ---
    {
        "topic": "React",
        "list": "situations",
        "text": "training for a marathon",
        "expected_relevant": False,
        "category": "clearly_irrelevant",
    },
    {
        "topic": "Python",
        "list": "situations",
        "text": "planning a wedding in six months",
        "expected_relevant": False,
        "category": "clearly_irrelevant",
    },
    {
        "topic": "SQL",
        "list": "contexts",
        "text": "learning watercolor painting as a hobby",
        "expected_relevant": False,
        "category": "clearly_irrelevant",
    },
    {
        "topic": "Public Speaking",
        "list": "situations",
        "text": "renovating the kitchen this summer",
        "expected_relevant": False,
        "category": "clearly_irrelevant",
    },

    # --- doc_failure_case: the exact regression this feature fixes ---
    {
        "topic": "React",
        "list": "situations",
        "text": "preparing for interview backend engineer",
        "expected_relevant": False,
        "category": "doc_failure_case",
    },
    {
        "topic": "Backend System Design",
        "list": "situations",
        "text": "preparing for interview backend engineer",
        "expected_relevant": True,
        "category": "doc_failure_case",
    },

    # --- urgency_casualness_confound: same relevance, different tone ---
    {
        "topic": "Frontend Development",
        "list": "situations",
        "text": "casually looking for frontend",
        "expected_relevant": True,
        "category": "urgency_casualness_confound",
    },
    {
        "topic": "Frontend Development",
        "list": "situations",
        "text": "urgently need frontend for a job I start Monday",
        "expected_relevant": True,
        "category": "urgency_casualness_confound",
    },
    {
        "topic": "Data Structures & Algorithms",
        "list": "situations",
        "text": "casually brushing up on DSA",
        "expected_relevant": True,
        "category": "urgency_casualness_confound",
    },
    {
        "topic": "Data Structures & Algorithms",
        "list": "situations",
        "text": "urgently cramming DSA before an interview tomorrow",
        "expected_relevant": True,
        "category": "urgency_casualness_confound",
    },

    # --- adjacent_distinct_domain: tests over-generalization ---
    {
        "topic": "React",
        "list": "situations",
        "text": "learning Vue at work",
        "expected_relevant": False,
        "category": "adjacent_distinct_domain",
    },
    {
        "topic": "Python",
        "list": "situations",
        "text": "writing Go microservices at work",
        "expected_relevant": False,
        "category": "adjacent_distinct_domain",
    },
    {
        "topic": "SQL",
        "list": "situations",
        "text": "learning MongoDB for a side project",
        "expected_relevant": False,
        "category": "adjacent_distinct_domain",
    },

    # --- ambiguous_hard: genuinely debatable, lower accuracy bar ---
    {
        "topic": "System Design",
        "list": "situations",
        "text": "preparing for interviews",
        "expected_relevant": True,
        "category": "ambiguous_hard",
    },
    {
        "topic": "Career Change",
        "list": "situations",
        "text": "casually looking for frontend",
        "expected_relevant": True,
        "category": "ambiguous_hard",
    },
    {
        "topic": "Data Structures & Algorithms",
        "list": "situations",
        "text": "preparing for interviews",
        "expected_relevant": True,
        "category": "ambiguous_hard",
    },

    # --- multi_topic: one situation, judged per-topic not globally ---
    {
        "topic": "React",
        "list": "situations",
        "text": "preparing for interview backend engineer",
        "expected_relevant": False,
        "category": "multi_topic",
    },
    {
        "topic": "Backend System Design",
        "list": "situations",
        "text": "preparing for interview backend engineer",
        "expected_relevant": True,
        "category": "multi_topic",
    },
    {
        "topic": "Job Interview Prep",
        "list": "situations",
        "text": "preparing for interview backend engineer",
        "expected_relevant": True,
        "category": "multi_topic",
    },
]
