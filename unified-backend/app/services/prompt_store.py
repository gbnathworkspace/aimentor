"""Mode → template mapping for mentor prompts.

Loads markdown prompt templates from app/prompts/ and interpolates
user context (profile, skill, episodes) into placeholders.
"""

import re
from pathlib import Path
from typing import Any

from app.models.chat import DEFAULT_TONE, ToneId

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# In-memory cache: filename → raw template string
_cache: dict[str, str] = {}

# Mode → template filename mapping
_MODE_TEMPLATES: dict[str, str] = {
    "planning": "mentor_v1.md",
    "topic": "mentor_v1.md",
    "doubt": "mentor_v1.md",
    "evaluation": "mentor_v1.md",
}

_ONBOARDING_TEMPLATE = "onboarding.md"

# Mode-specific instruction blocks appended to the base mentor template
_MODE_INSTRUCTIONS: dict[str, str] = {
    "planning": (
        "You are in PLANNING mode. Your job is to help the user create a concrete study plan.\n"
        "- Identify the 1-2 highest priority topics based on gap size and time remaining.\n"
        "- Translate priorities into a concrete weekly study plan with hours and deliverables.\n"
        "- If the user picks a topic that isn't the highest priority, push back with data.\n"
        "- Factor in their daily availability — don't overcommit.\n"
        "- Do NOT start teaching. Planning is the entire goal of this session."
    ),
    "topic": (
        "You are in TOPIC mode. Your job is to teach the user about the current topic.\n"
        "- Start by probing what they already know — don't re-explain things covered before.\n"
        "- Focus on weak areas. Skip strong areas unless asked.\n"
        "- Teach through explanation + targeted questions. Don't monologue.\n"
        "- Use Socratic method: explain → apply → push edge cases.\n"
        "- Calibrate difficulty to the user's current level.\n"
        "- Track understanding as you go — name struggling concepts explicitly."
    ),
    "doubt": (
        "You are in DOUBT mode. The user has a specific doubt or confusion to resolve.\n"
        "- Let them state the doubt fully before responding.\n"
        "- Give a clear, precise answer. Don't pad with unrequested background.\n"
        "- Reference relevant past sessions if applicable.\n"
        "- After resolving, ask one targeted question to confirm understanding.\n"
        "- If the doubt reveals a deeper gap, name it and suggest a dedicated session.\n"
        "- Keep it short and focused. Doubt resolution is the goal, not comprehensive coverage."
    ),
    "evaluation": (
        "You are in EVALUATION mode. Your job is to assess proficiency — not to teach.\n"
        "- Run a 3-level question sequence: Recall → Application → Depth.\n"
        "- Ask one question at a time. Wait for the answer before proceeding.\n"
        "- Do not give hints or rephrase questions if they struggle.\n"
        "- After each answer, give a brief verdict: Strong / Partial / Weak.\n"
        "- After all levels, provide a final summary with gaps and strengths.\n"
        "- Do NOT confirm correct answers mid-evaluation."
    ),
}


# Tone → voice instruction. The single source of truth for what each tone DOES.
# Keyed by ToneId; the frontend only knows the ids (data.ts), never this text.
_TONE_INSTRUCTIONS: dict[str, str] = {
    "tough": (
        "Adopt a TOUGH voice. Be blunt and demanding. Do not soften feedback or "
        "cushion gaps — name them directly. Hold a high bar and expect rigour."
    ),
    "balanced": (
        "Adopt a BALANCED voice. Be supportive but honest. Encourage effort, but "
        "name weaknesses plainly. Neither harsh nor coddling."
    ),
    "encouraging": (
        "Adopt an ENCOURAGING voice. Lead with warmth and affirmation. Frame gaps "
        "as progress and next steps. Stay positive while still being truthful."
    ),
}


def _load_template(filename: str) -> str:
    """Load a template file from the prompts directory, with caching."""
    if filename in _cache:
        return _cache[filename]

    filepath = _PROMPTS_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Prompt template not found: {filepath}")

    content = filepath.read_text(encoding="utf-8")
    _cache[filename] = content
    return content


def _interpolate(template: str, variables: dict[str, str]) -> str:
    """Replace {{variable_name}} placeholders with values from variables dict.

    Missing variables are replaced with empty string to avoid breaking the prompt.
    """
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, "")

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def _format_documents(documents: list[dict[str, Any]]) -> str:
    """Format ingested file chunks into a readable block for the prompt."""
    if not documents:
        return "(no uploaded documents)"

    lines = []
    for doc in documents:
        filename = (doc.get("metadata") or {}).get("filename", "uploaded file")
        text = doc.get("text", "")
        lines.append(f"[{filename}] {text}")
    return "\n\n".join(lines)


def _format_episodes(episodes: list[dict[str, Any]]) -> str:
    """Format episodic memory entries into a readable block for the prompt."""
    if not episodes:
        return "(no prior sessions found)"

    lines = []
    for i, ep in enumerate(episodes, 1):
        title = ep.get("title", "Untitled session")
        summary = ep.get("summary", "")
        topic = ep.get("topic", "")
        date = ep.get("date", "")

        # Truncate long summaries
        if len(summary) > 300:
            summary = summary[:300] + "…"

        header = f"[{i}] {title}"
        if topic:
            header += f" [{topic}]"
        if date:
            header += f" — {date}"

        lines.append(f"{header}\n{summary}")

    return "\n\n".join(lines)


def _build_context_variables(
    context: dict[str, Any], mode: str, tone: ToneId
) -> dict[str, str]:
    """Extract template variables from the assembled context dict."""
    profile = context.get("profile", {})
    skill = context.get("skill", {})
    episodes = context.get("episodes", [])

    return {
        # L1 Profile fields
        "goal": profile.get("goal", "Not specified"),
        "deadline": profile.get("deadline", "Not specified"),
        "overall_level": profile.get("overall_level", "beginner"),
        "daily_availability": profile.get("daily_availability", "Not specified"),
        # L2 Skill fields
        "topic": skill.get("topic", context.get("topic", "General")),
        "required_level": skill.get("required_level", "Not assessed"),
        "current_level": skill.get("current_level", "Not assessed"),
        "gap": skill.get("gap", "Unknown"),
        # L3 Episodes
        "episodes": _format_episodes(episodes),
        # Uploaded documents (ingested files)
        "documents": _format_documents(context.get("documents", [])),
        # Mode
        "mode": mode,
        "mode_instructions": _MODE_INSTRUCTIONS.get(mode, ""),
        # Tone
        "tone_instructions": _TONE_INSTRUCTIONS.get(tone, _TONE_INSTRUCTIONS[DEFAULT_TONE]),
    }


def get_system_prompt(
    mode: str, context: dict[str, Any], tone: ToneId = DEFAULT_TONE
) -> str:
    """Load and format the system prompt for a given mentor mode.

    Args:
        mode: One of "planning", "topic", "doubt", "evaluation".
        context: Dict with keys "profile", "skill", "episodes" from context_assembler.
        tone: Mentor voice (tough/balanced/encouraging). Defaults to DEFAULT_TONE.

    Returns:
        The fully interpolated system prompt string.

    Raises:
        ValueError: If the mode is not recognized.
        FileNotFoundError: If the template file is missing.
    """
    if mode not in _MODE_TEMPLATES:
        raise ValueError(
            f"Unknown mode '{mode}'. Must be one of: {', '.join(_MODE_TEMPLATES.keys())}"
        )

    template_file = _MODE_TEMPLATES[mode]
    template = _load_template(template_file)
    variables = _build_context_variables(context, mode, tone)

    return _interpolate(template, variables)


def get_onboarding_prompt() -> str:
    """Load the onboarding system prompt with today's date injected.

    The date lets the model convert a relative timeframe ("3 months") into an
    absolute ``YYYY-MM-DD`` deadline (parity with the original Next.js prompt).
    """
    import datetime

    template = _load_template(_ONBOARDING_TEMPLATE)
    today = datetime.date.today().isoformat()
    return (
        f"{template}\n\nToday's date is {today}. When the user gives a relative "
        f"timeframe (e.g. \"3 months\"), compute and output `deadline` as an "
        f"absolute YYYY-MM-DD date relative to today."
    )


def clear_cache() -> None:
    """Clear the template cache. Useful for tests or hot-reloading."""
    _cache.clear()
