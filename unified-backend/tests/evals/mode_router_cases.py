"""Hand-labeled cases for the mode_router eval (route_user_turn's rule
selection quality — see app/services/mode_router.py's Rule 1-6 decision
tree).

Each case gives the inputs route_user_turn() takes (query, skill, recent
turns, optional profile) plus the expected_mode a human reviewer picked.
Rule 1 (cold start) is a plain Python check with no LLM call — its cases
exist here as a cheap sanity check, not because they exercise the router
model. Rules 2-6 are real Haiku tool_use calls being judged for quality.

Scope note: same rationale as classify_relevance_cases.py — a small,
actually-reviewed set beats a padded one nobody checked. ~3-4 cases per
category, every rule represented at least once.
"""

EVAL_CASES = [
    # --- rule1_cold_start: no assessment yet, plain Python short-circuit ---
    {
        "query": "teach me about closures in JS",
        "skill": {},
        "recent_messages": [],
        "expected_mode": "DIAGNOSTIC",
        "category": "rule1_cold_start",
    },
    {
        "query": "let's start on React hooks",
        "skill": {"assessed": False},
        "recent_messages": [],
        "expected_mode": "DIAGNOSTIC",
        "category": "rule1_cold_start",
    },

    # --- rule2_urgency_direct: explicit direct-answer or factual lookup ---
    {
        "query": "just tell me the answer, what's the time complexity of quicksort worst case?",
        "skill": {"current_level": "intermediate", "required_level": "advanced", "gap": "30%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "DIRECT",
        "category": "rule2_urgency_direct",
    },
    {
        "query": "what port does HTTPS use?",
        "skill": {"current_level": "beginner", "required_level": "intermediate", "gap": "40%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "DIRECT",
        "category": "rule2_urgency_direct",
    },
    {
        "query": "syntax for pushing to an array in JS",
        "skill": {"current_level": "beginner", "required_level": "beginner", "gap": "0%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "DIRECT",
        "category": "rule2_urgency_direct",
    },
    {
        "query": "no rush but can you just give me the exact npm command to install React Router",
        "skill": {"current_level": "beginner", "required_level": "intermediate", "gap": "25%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "DIRECT",
        "category": "rule2_urgency_direct",
    },

    # --- rule3_high_frustration: repeated failed attempts or explicit frustration ---
    {
        "query": "still getting the same TypeError, I've tried three different fixes and nothing works",
        "skill": {"current_level": "beginner", "required_level": "intermediate", "gap": "35%", "assessed": True},
        "recent_messages": [
            {"type": "message", "role": "user", "content": "I tried adding a null check but it still throws"},
            {"type": "message", "role": "mentor", "content": "Try guarding the array access before the map call."},
            {"type": "message", "role": "user", "content": "Did that, still broken, tried a try/catch too"},
            {"type": "message", "role": "mentor", "content": "Can you share the updated code?"},
        ],
        "expected_mode": "GUIDED",
        "category": "rule3_high_frustration",
    },
    {
        "query": "I'm completely lost, I don't even know where to start with this whole authentication flow",
        "skill": {"current_level": "beginner", "required_level": "advanced", "gap": "60%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "GUIDED",
        "category": "rule3_high_frustration",
    },
    {
        "query": "nothing I try fixes this recursion bug, I've been stuck for an hour",
        "skill": {"current_level": "intermediate", "required_level": "advanced", "gap": "20%", "assessed": True},
        "recent_messages": [
            {"type": "message", "role": "user", "content": "my recursive function isn't terminating"},
            {"type": "message", "role": "mentor", "content": "Check your base case."},
            {"type": "message", "role": "user", "content": "added one, still infinite looping"},
        ],
        "expected_mode": "GUIDED",
        "category": "rule3_high_frustration",
    },

    # --- rule4_single_error_hint: one attempt, one specific blind spot ---
    {
        "query": (
            "I wrote this to reverse a linked list but it only reverses the first two nodes:\n"
            "def reverse(head):\n"
            "    prev = None\n"
            "    curr = head\n"
            "    next = curr.next\n"
            "    curr.next = prev\n"
            "    return curr"
        ),
        "skill": {"current_level": "intermediate", "required_level": "intermediate", "gap": "10%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "HINT",
        "category": "rule4_single_error_hint",
    },
    {
        "query": "I used useEffect with an empty dependency array but my state still isn't updating on prop changes, here's my component: useEffect(() => { setValue(props.value) }, [])",
        "skill": {"current_level": "intermediate", "required_level": "advanced", "gap": "15%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "HINT",
        "category": "rule4_single_error_hint",
    },
    {
        "query": "my SQL query returns duplicate rows, I think it's my JOIN but not sure why: SELECT * FROM orders o JOIN order_items oi ON o.id = oi.order_id",
        "skill": {"current_level": "beginner", "required_level": "intermediate", "gap": "20%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "HINT",
        "category": "rule4_single_error_hint",
    },

    # --- rule5_zero_attempt_socratic: broad conceptual ask, no attempt yet ---
    {
        "query": "what is a hash map and how does it actually work under the hood?",
        "skill": {"current_level": "beginner", "required_level": "intermediate", "gap": "30%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "SOCRATIC",
        "category": "rule5_zero_attempt_socratic",
    },
    {
        "query": "how would you approach designing a URL shortener?",
        "skill": {"current_level": "intermediate", "required_level": "advanced", "gap": "25%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "SOCRATIC",
        "category": "rule5_zero_attempt_socratic",
    },
    {
        "query": "can you explain how garbage collection works in the JVM?",
        "skill": {"current_level": "beginner", "required_level": "intermediate", "gap": "35%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "SOCRATIC",
        "category": "rule5_zero_attempt_socratic",
    },

    # --- urgency_casualness_confound: casual tone shouldn't override the actual rule ---
    {
        "query": "hey no rush at all, just wondering — what's the exact syntax for a JS array push again?",
        "skill": {"current_level": "beginner", "required_level": "beginner", "gap": "0%", "assessed": True},
        "recent_messages": [],
        "expected_mode": "DIRECT",
        "category": "urgency_casualness_confound",
    },
    {
        "query": "whenever you get a chance, urgent-ish — I have 2 failed deploys in a row and nothing I change fixes the build error",
        "skill": {"current_level": "intermediate", "required_level": "advanced", "gap": "20%", "assessed": True},
        "recent_messages": [
            {"type": "message", "role": "user", "content": "build fails with a module resolution error"},
            {"type": "message", "role": "mentor", "content": "Try clearing node_modules and reinstalling."},
            {"type": "message", "role": "user", "content": "did that, same error, tried changing the import path too"},
        ],
        "expected_mode": "GUIDED",
        "category": "urgency_casualness_confound",
    },
]
