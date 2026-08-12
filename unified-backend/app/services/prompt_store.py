"""Mode → template mapping for mentor prompts.

Loads markdown prompt templates from app/prompts/ and interpolates
user context (profile, skill, episodes) into placeholders.
"""

import re
from pathlib import Path
from typing import Any

from app.models.chat import DEFAULT_TONE, ToneId
from app.services.skill_graph_repo import next_best_topics

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# In-memory cache: filename → raw template string
_cache: dict[str, str] = {}

# Mode → template filename mapping
_MODE_TEMPLATES: dict[str, str] = {
    "planning": "mentor_v1.md",
    "doubt": "mentor_v1.md",
    "evaluation": "mentor_v1.md",
    # Routed sub-modes for "topic" turns — selected per-turn by
    # mode_router.route_user_turn() instead of one static "topic" block
    # that used to give contradictory instructions.
    "diagnostic": "mentor_v1.md",
    "direct": "mentor_v1.md",
    "socratic": "mentor_v1.md",
    "hint": "mentor_v1.md",
    "guided": "mentor_v1.md",
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
    # Routed sub-modes for "topic" turns (see mode_router.py). Each is
    # self-contained — no shared universal "always end with a question"
    # suffix, since that used to defeat DIRECT's whole purpose.
    "diagnostic": (
        "You are running a brief DIAGNOSTIC before teaching this topic.\n"
        "- Ask 1-2 targeted questions to gauge the student's actual current "
        "level (beginner/intermediate/advanced/expert). Do NOT teach content "
        "yet, do NOT give the full picture up front. This holds even if the "
        "user's profile below says they prefer answer-first explanations — "
        "that preference shapes how you teach once diagnosis is done, it "
        "does not skip diagnosis.\n"
        "- If Relevant Past Sessions below show related experience, let it "
        "inform your first question's difficulty, but still verify — don't "
        "skip diagnosis on assumption.\n"
        "- Use the quick-reply option format for questions with discrete "
        "plausible answers.\n"
        "- Once the user's answer gives you enough signal, call the "
        "record_diagnostic_verdict tool with your assessment, and tell them "
        "their level in one line before moving into teaching."
    ),
    "direct": (
        "You are in DIRECT mode. The user wants a direct, concise answer — "
        "a factual lookup, syntax question, or explicit request to skip "
        "the back-and-forth.\n"
        "- Answer immediately and completely. No preamble, no leading "
        "question, no withholding.\n"
        "- Do not end the reply with a question — that defeats the point "
        "of this mode."
    ),
    "socratic": (
        "You are in SOCRATIC mode. The user hasn't attempted this yet, or "
        "you're activating prior knowledge before teaching.\n"
        "- Do not give away the solution or full explanation.\n"
        "- Pose a targeted leading question that makes them use what they "
        "already know to take the first step.\n"
        "- Calibrate difficulty to the user's current level.\n"
        "- End with a question — the student should reply before you teach."
    ),
    "hint": (
        "You are in HINT mode. The user made an attempt and hit a specific, "
        "targeted point of confusion — not yet frustrated, not a repeated "
        "failure.\n"
        "- Name the specific gap or misapplied concept in their attempt.\n"
        "- Point at the blind spot without handing over the fully corrected "
        "answer — a nudge, not a solve.\n"
        "- End with a question that lets them try the fix themselves."
    ),
    "guided": (
        "You are in GUIDED mode. The user is stuck on a multi-step problem "
        "or showing real frustration (repeated failed attempts, explicit "
        "'I'm lost' language).\n"
        "- De-escalate. Break the problem into simple sub-steps.\n"
        "- Walk through step 1 only — don't dump the remaining steps at "
        "once.\n"
        "- End with a check that they've got step 1 before continuing."
    ),
    "doubt": (
        "You are in DOUBT mode. The user has a specific doubt or confusion to resolve.\n"
        "- Let them state the doubt fully before responding.\n"
        "- Attempt-first: ask what they think or have tried before resolving it. Lead with a "
        "hint, escalate only if they're still stuck (hint → worked step → answer), and fade "
        "this ladder as the Current Level rises — advanced students get a direct answer faster.\n"
        "- Give a clear, precise answer once they've engaged. Don't pad with unrequested background.\n"
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


def _format_learning_context(profile: dict[str, Any]) -> str:
    """Format every context + every situation the user has recorded.

    Nothing here is "active" — the user curates the lists, and whatever is in
    them is true of them right now, so all of it is injected.
    """
    detail = profile.get("learning_context_detail") or {}
    contexts = list(detail.get("contexts") or [])
    if not contexts and profile.get("learning_context"):
        contexts = [str(profile["learning_context"])]

    situations = list(detail.get("situations") or [])
    # `label` predates `situations` (onboarding/memory_editor still write it).
    label = detail.get("label")
    if label and label not in situations:
        situations.insert(0, label)

    parts = [p for p in (", ".join(contexts), "; ".join(situations)) if p]
    return " — ".join(parts) if parts else "Not specified"


def _format_focus_areas(profile: dict[str, Any]) -> str:
    """Format the L1 focus_areas list for the prompt."""
    areas = profile.get("focus_areas") or []
    return ", ".join(areas) if areas else "Not specified"


def _format_style_notes(style_notes: list[dict[str, Any]]) -> str:
    """Format observed StyleNote entries into a readable bullet list."""
    if not style_notes:
        return "(none observed yet)"
    return "\n".join(
        f"- [{note.get('category', 'context')}] {note.get('note', '')}"
        for note in style_notes
    )


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


def _format_next_skills(skill_graph: list[dict[str, Any]]) -> str:
    """Format the prerequisite-ordered next-best-skill sequence (issue #10)."""
    ranked = next_best_topics(skill_graph)
    if not ranked:
        return "(no pending topics — skill graph empty or fully mastered)"
    return "\n".join(f"{i}. {item['topic']} (gap: {item['gap']})" for i, item in enumerate(ranked, 1))


def _build_context_variables(
    context: dict[str, Any], mode: str, tone: ToneId
) -> dict[str, str]:
    """Extract template variables from the assembled context dict."""
    profile = context.get("profile", {})
    skill = context.get("skill", {})
    episodes = context.get("episodes", [])

    mode_instructions = _MODE_INSTRUCTIONS.get(mode, "")
    if mode == "planning":
        mode_instructions += (
            "\n- Suggested next-best-skill order (prerequisites-first, unmastered only):\n"
            + _format_next_skills(context.get("skill_graph") or [])
        )

    return {
        # L1 Profile fields
        "learning_context": _format_learning_context(profile),
        "focus_areas": _format_focus_areas(profile),
        "explanation_style": profile.get("explanation_style", "hint-first"),
        "challenge_tolerance": profile.get("challenge_tolerance", "medium"),
        "feedback_tone": profile.get("feedback_tone", "encouraging"),
        # Observed teaching-style notes, grounded per-session (issue #14 evolution)
        "style_notes": _format_style_notes(profile.get("style_notes") or []),
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
        "mode_instructions": mode_instructions,
        # Tone
        "tone_instructions": _TONE_INSTRUCTIONS.get(tone, _TONE_INSTRUCTIONS[DEFAULT_TONE]),
    }


def get_system_prompt(
    mode: str, context: dict[str, Any], tone: ToneId = DEFAULT_TONE
) -> str:
    """Load and format the system prompt for a given mentor mode.

    Args:
        mode: One of "planning", "doubt", "evaluation", or a routed topic
            sub-mode from mode_router.py ("diagnostic", "direct", "socratic",
            "hint", "guided").
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
    """Load the onboarding system prompt."""
    return _load_template(_ONBOARDING_TEMPLATE)


def clear_cache() -> None:
    """Clear the template cache. Useful for tests or hot-reloading."""
    _cache.clear()
