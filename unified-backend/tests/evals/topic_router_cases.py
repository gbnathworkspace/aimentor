"""Hand-labeled cases for the topic_router eval (route_topic's MATCH /
AMBIGUOUS / NEW decision quality — see app/services/topic_router.py).

Each case gives route_topic()'s inputs (query, candidate topics) plus a
human-reviewed `expected` verdict:

- {"decision": "MATCH", "topic_id": "t1"} — exactly one topic is the right
  continuation. Correct iff the router MATCHes that exact id, OR marks it
  AMBIGUOUS with that id among the related_ids (still a good outcome — the
  user sees it in the pick-list instead of losing it to a false NEW).
- {"decision": "AMBIGUOUS", "acceptable": ["t1", "t2"]} — several topics
  genuinely overlap; there's no single right pick a human reviewer would
  insist on. Correct iff the router surfaces at least one acceptable id,
  either as a confident MATCH or inside an AMBIGUOUS related_ids list.
  Wrong only if it says NEW (misses the relatedness entirely) or names
  something outside the acceptable set.
- {"decision": "NEW"} — nothing in the topic list is a plausible
  continuation. Correct iff the router returns no topic_id and no
  related_ids.

Scope note: same rationale as classify_relevance_cases.py / mode_router_cases.py
— a small, actually-reviewed set beats a padded one. ~4 cases per category,
plus one no-candidates sanity case that costs no LLM call.
"""

EVAL_CASES = [
    # --- clear_match: exactly one topic fits, unambiguously ---
    {
        "query": "explain the useEffect hook and why my state is stale",
        "topics": [
            {"topicId": "t1", "title": "React", "subject": "Frontend"},
            {"topicId": "t2", "title": "SQL Basics", "subject": ""},
            {"topicId": "t3", "title": "Public Speaking", "subject": ""},
        ],
        "expected": {"decision": "MATCH", "topic_id": "t1"},
        "category": "clear_match",
    },
    {
        "query": "how do decorators work in python?",
        "topics": [
            {"topicId": "t1", "title": "Python Basics", "subject": ""},
            {"topicId": "t2", "title": "Go Microservices", "subject": "Backend"},
            {"topicId": "t3", "title": "Kubernetes", "subject": ""},
        ],
        "expected": {"decision": "MATCH", "topic_id": "t1"},
        "category": "clear_match",
    },
    {
        "query": "how would I design a URL shortener for my interview prep?",
        "topics": [
            {"topicId": "t1", "title": "System Design Interview Prep", "subject": ""},
            {"topicId": "t2", "title": "Guitar Lessons", "subject": ""},
        ],
        "expected": {"decision": "MATCH", "topic_id": "t1"},
        "category": "clear_match",
    },
    {
        "query": "explain inner join vs left join",
        "topics": [
            {"topicId": "t1", "title": "SQL Basics", "subject": ""},
        ],
        "expected": {"decision": "MATCH", "topic_id": "t1"},
        "category": "clear_match",
    },

    # --- clear_new: nothing in the list is a plausible continuation ---
    {
        "query": "help me plan a wedding budget",
        "topics": [
            {"topicId": "t1", "title": "React", "subject": "Frontend"},
            {"topicId": "t2", "title": "SQL Basics", "subject": ""},
        ],
        "expected": {"decision": "NEW"},
        "category": "clear_new",
    },
    {
        "query": "give me a training plan for my first marathon",
        "topics": [
            {"topicId": "t1", "title": "Python Basics", "subject": ""},
        ],
        "expected": {"decision": "NEW"},
        "category": "clear_new",
    },
    {
        "query": "recommend a good sourdough bread recipe",
        "topics": [
            {"topicId": "t1", "title": "Kubernetes", "subject": ""},
            {"topicId": "t2", "title": "AWS Networking", "subject": ""},
        ],
        "expected": {"decision": "NEW"},
        "category": "clear_new",
    },
    {
        "query": "explain how binary search trees work",
        "topics": [
            {"topicId": "t1", "title": "Public Speaking", "subject": ""},
            {"topicId": "t2", "title": "Guitar Lessons", "subject": ""},
        ],
        "expected": {"decision": "NEW"},
        "category": "clear_new",
    },

    # --- ambiguous: genuine overlap between 2+ topics, no single right answer ---
    {
        "query": "how do I manage state in my app",
        "topics": [
            {"topicId": "t1", "title": "React", "subject": "Frontend"},
            {"topicId": "t2", "title": "React Native", "subject": "Mobile"},
        ],
        "expected": {"decision": "AMBIGUOUS", "acceptable": ["t1", "t2"]},
        "category": "ambiguous",
    },
    {
        "query": "explain list comprehensions in python",
        "topics": [
            {"topicId": "t1", "title": "Python Basics", "subject": ""},
            {"topicId": "t2", "title": "Python for Data Science", "subject": ""},
        ],
        "expected": {"decision": "AMBIGUOUS", "acceptable": ["t1", "t2"]},
        "category": "ambiguous",
    },
    {
        "query": "how do containers talk to each other over the network?",
        "topics": [
            {"topicId": "t1", "title": "Kubernetes", "subject": ""},
            {"topicId": "t2", "title": "AWS Networking", "subject": ""},
            {"topicId": "t3", "title": "Docker", "subject": ""},
        ],
        "expected": {"decision": "AMBIGUOUS", "acceptable": ["t1", "t2", "t3"]},
        "category": "ambiguous",
    },
    {
        "query": "preparing for interviews next month, not sure where to start",
        "topics": [
            {"topicId": "t1", "title": "Job Interview Prep", "subject": ""},
            {"topicId": "t2", "title": "System Design Interview Prep", "subject": ""},
            {"topicId": "t3", "title": "Data Structures & Algorithms", "subject": ""},
        ],
        "expected": {"decision": "AMBIGUOUS", "acceptable": ["t1", "t2", "t3"]},
        "category": "ambiguous",
    },

    # --- title_substring_confound: the failure mode the old keyword-overlap
    # heuristic (detectTopic.ts) was prone to — a superficial title/word
    # match that isn't the actual right topic. ---
    {
        "query": "explain closures and arrow functions",
        "topics": [
            {"topicId": "t1", "title": "Java", "subject": "Programming"},
            {"topicId": "t2", "title": "JavaScript", "subject": "Frontend"},
        ],
        "expected": {"decision": "MATCH", "topic_id": "t2"},
        "category": "title_substring_confound",
    },
    {
        "query": "how do I write a query that joins two tables?",
        "topics": [
            {"topicId": "t1", "title": "SQL Basics", "subject": ""},
            {"topicId": "t2", "title": "NoSQL Databases", "subject": ""},
        ],
        "expected": {"decision": "MATCH", "topic_id": "t1"},
        "category": "title_substring_confound",
    },

    # --- no_candidates: sanity check, no LLM call at all ---
    {
        "query": "anything at all",
        "topics": [],
        "expected": {"decision": "NEW"},
        "category": "no_candidates",
    },
]
