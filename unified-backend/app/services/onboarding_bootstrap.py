"""Goal → skills derivation during onboarding.

Provides:
- GOAL_KNOWLEDGE_BASE: predefined skill topics for common learning goals
- compute_gap(required, current): gap calculation between skill levels
- bootstrap_skills(user_id, goal, overall_level): async function to generate and persist skill nodes
"""

import json
import logging
from typing import Optional

import anthropic

from app.config.database import skill_graph_col
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Ordered skill levels from lowest to highest
LEVEL_ORDER = ["beginner", "intermediate", "advanced", "expert"]

# Predefined skill topics for common learning goals
GOAL_KNOWLEDGE_BASE: dict[str, list[str]] = {
    "crack faang interviews": [
        "Data Structures",
        "Algorithms",
        "System Design",
        "Behavioral Interviews",
        "Problem Solving",
    ],
    "learn system design": [
        "Distributed Systems",
        "Database Design",
        "Caching",
        "Load Balancing",
        "Microservices",
    ],
    "learn python": [
        "Python Basics",
        "Data Types",
        "Functions",
        "OOP",
        "Standard Library",
    ],
    "learn machine learning": [
        "Linear Algebra",
        "Statistics",
        "Supervised Learning",
        "Neural Networks",
        "Model Evaluation",
    ],
    "learn web development": [
        "HTML/CSS",
        "JavaScript",
        "React",
        "APIs/REST",
        "Databases",
    ],
    "learn data science": [
        "Statistics",
        "Python for Data Science",
        "Data Visualization",
        "Pandas/NumPy",
        "Machine Learning Basics",
    ],
    "learn devops": [
        "Linux Fundamentals",
        "Docker",
        "CI/CD Pipelines",
        "Cloud Services",
        "Infrastructure as Code",
    ],
    "learn cloud computing": [
        "Cloud Fundamentals",
        "Compute Services",
        "Storage and Databases",
        "Networking",
        "Security and IAM",
    ],
    "learn mobile development": [
        "Mobile UI Fundamentals",
        "React Native/Flutter",
        "State Management",
        "API Integration",
        "App Deployment",
    ],
    "learn databases": [
        "SQL Fundamentals",
        "Data Modeling",
        "Indexing and Performance",
        "NoSQL Databases",
        "Transactions and ACID",
    ],
    "learn cybersecurity": [
        "Network Security",
        "Cryptography",
        "Vulnerability Assessment",
        "Secure Coding",
        "Incident Response",
    ],
    "learn ai": [
        "Machine Learning Fundamentals",
        "Deep Learning",
        "Natural Language Processing",
        "Computer Vision",
        "AI Ethics",
    ],
}


def compute_gap(required: str, current: str) -> str:
    """Compute the gap between required and current skill levels.

    Level order: beginner < intermediate < advanced < expert

    Returns:
        "none" if current >= required
        "small" if 1 level difference
        "medium" if 2 levels difference
        "large" if 3 levels difference
    """
    required_lower = required.lower().strip()
    current_lower = current.lower().strip()

    # Default to intermediate/beginner if unrecognized
    required_idx = (
        LEVEL_ORDER.index(required_lower)
        if required_lower in LEVEL_ORDER
        else LEVEL_ORDER.index("intermediate")
    )
    current_idx = (
        LEVEL_ORDER.index(current_lower)
        if current_lower in LEVEL_ORDER
        else LEVEL_ORDER.index("beginner")
    )

    diff = required_idx - current_idx

    if diff <= 0:
        return "none"
    elif diff == 1:
        return "small"
    elif diff == 2:
        return "medium"
    else:
        return "large"


def _lookup_goal_in_kb(goal: str) -> Optional[list[str]]:
    """Fuzzy match goal against the knowledge base.

    Checks if any KB key is a substring of the goal or vice versa.
    """
    normalized = goal.lower().strip()

    # Direct match
    if normalized in GOAL_KNOWLEDGE_BASE:
        return GOAL_KNOWLEDGE_BASE[normalized]

    # Check if any KB key is a substring of the goal or vice versa
    for kb_key, topics in GOAL_KNOWLEDGE_BASE.items():
        if kb_key in normalized or normalized in kb_key:
            return topics

    return None


async def _generate_topics_via_llm(goal: str) -> list[str]:
    """Call Anthropic to generate 4-6 skill topics for the given goal."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": (
                    f"List exactly 5 key skill topics someone needs to learn to achieve this goal: '{goal}'. "
                    "Return ONLY a JSON array of strings, no explanation. Example: "
                    '[\"Topic 1\", \"Topic 2\", \"Topic 3\", \"Topic 4\", \"Topic 5\"]'
                ),
            }
        ],
    )

    text = response.content[0].text.strip()

    # Try to parse the response as JSON array
    try:
        topics = json.loads(text)
        if isinstance(topics, list) and all(isinstance(t, str) for t in topics):
            return topics[:6]  # Cap at 6 topics
    except json.JSONDecodeError:
        pass

    # Fallback: try to extract JSON array from the text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            topics = json.loads(text[start : end + 1])
            if isinstance(topics, list) and all(isinstance(t, str) for t in topics):
                return topics[:6]
        except json.JSONDecodeError:
            pass

    # Last resort: split by newlines and clean up
    lines = [line.strip().strip("-•*").strip() for line in text.split("\n") if line.strip()]
    return [line for line in lines if line and len(line) < 100][:6]


async def bootstrap_skills(
    user_id: str, goal: str, overall_level: str = "beginner"
) -> list[dict]:
    """Generate and persist skill graph nodes for a user's goal.

    Args:
        user_id: The authenticated user's ID
        goal: The user's stated learning goal
        overall_level: The user's self-assessed overall level (default "beginner")

    Returns:
        List of skill node dicts that were upserted
    """
    # Normalize goal
    normalized_goal = goal.lower().strip()

    # Look up in knowledge base (fuzzy match)
    topics = _lookup_goal_in_kb(normalized_goal)

    # If not found in KB, generate via LLM
    if topics is None:
        logger.info(f"Goal '{goal}' not in KB, generating topics via LLM")
        topics = await _generate_topics_via_llm(goal)

    if not topics:
        logger.warning(f"No topics generated for goal '{goal}'")
        return []

    # Determine required_level based on goal complexity (default "intermediate")
    required_level = "intermediate"

    # Current level comes from the user's overall_level input
    current_level = overall_level.lower().strip() if overall_level else "beginner"
    if current_level not in LEVEL_ORDER:
        current_level = "beginner"

    # Build skill nodes and upsert into DB
    skill_nodes = []
    for topic in topics:
        gap = compute_gap(required_level, current_level)
        node = {
            "user_id": user_id,
            "topic": topic,
            "required_level": required_level,
            "current_level": current_level,
            "gap": gap,
        }

        # Upsert into skill_graph collection
        await skill_graph_col().update_one(
            {"user_id": user_id, "topic": topic},
            {"$set": node},
            upsert=True,
        )

        skill_nodes.append(node)

    logger.info(
        f"Bootstrapped {len(skill_nodes)} skills for user '{user_id}' with goal '{goal}'"
    )
    return skill_nodes
