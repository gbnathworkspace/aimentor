"""LLM summarization + skill update on session end.

Generates a structured summary via Anthropic tool_use pattern,
persists the summary as an episodic memory entry with embedding,
and upserts the skill graph node.

Partial failure strategy:
- LLM call fails → raise (returns 500 to caller)
- Embedding fails → persist without embedding (embed_text returns [])
- Skill graph update fails → log warning, continue
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

import anthropic

from app.config.database import sessions_col, skill_graph_col
from app.config.settings import get_settings
from app.services.embedder import embed_text

logger = logging.getLogger(__name__)

SUMMARISE_TOOL = {
    "name": "save_session_summary",
    "description": "Produce a structured summary of the learning session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the session",
            },
            "narrative_summary": {
                "type": "string",
                "description": "2-3 sentence narrative summary",
            },
            "skill_update": {
                "type": "object",
                "description": "Optional skill level update derived from the session",
                "properties": {
                    "current_level": {
                        "type": "string",
                        "description": "Updated skill level (beginner, intermediate, advanced, expert)",
                    },
                    "signals": {
                        "type": "object",
                        "description": "Evidence signals for the level assessment",
                    },
                },
            },
        },
        "required": ["title", "narrative_summary"],
    },
}


def _extract_tool_use(response, tool_name: str) -> dict:
    """Extract the input dict from a tool_use content block in the Anthropic response.

    Args:
        response: The Anthropic messages response object.
        tool_name: The name of the tool to find in the response.

    Returns:
        The tool input dictionary. Returns empty dict if not found.
    """
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    logger.warning("Tool use block '%s' not found in LLM response", tool_name)
    return {}


async def process_session_end(
    user_id: str, topic: str, messages: list[dict]
) -> dict:
    """Generate summary via LLM, persist as episodic entry, update skill graph.

    Args:
        user_id: The authenticated user's ID.
        topic: The session topic.
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        Dict with session_id, title, summary, and skill_update.

    Raises:
        Exception: If the LLM call fails (propagates to caller as 500).
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build transcript from messages
    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    # Call Anthropic with tool_use pattern for structured output
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[SUMMARISE_TOOL],
        tool_choice={"type": "tool", "name": "save_session_summary"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarise this session on '{topic}'.\n\n"
                    f"<transcript>\n{transcript}\n</transcript>"
                ),
            }
        ],
    )

    # Extract structured data from tool_use response
    summary_data = _extract_tool_use(response, "save_session_summary")
    title = summary_data.get("title", f"Session on {topic}")
    narrative = summary_data.get("narrative_summary", "")
    skill_update = summary_data.get("skill_update", {})

    # Generate embedding for the narrative (returns [] on failure)
    session_id = str(uuid4())
    vector = await embed_text(narrative)

    # Persist episodic entry
    entry = {
        "user_id": user_id,
        "session_id": session_id,
        "topic": topic,
        "title": title,
        "summary": narrative,
        "skill_update": skill_update,
        "embedding": vector,
        "type": "session",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await sessions_col().insert_one(entry)

    # Upsert skill graph (non-critical — log and continue on failure)
    if skill_update and skill_update.get("current_level"):
        try:
            await skill_graph_col().update_one(
                {"user_id": user_id, "topic": topic},
                {
                    "$set": {
                        "current_level": skill_update["current_level"],
                        "signals": skill_update.get("signals", {}),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("Skill graph update failed: %s", str(e))

    return {
        "session_id": session_id,
        "title": title,
        "summary": narrative,
        "skill_update": skill_update,
    }
