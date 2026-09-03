"""Mode → template mapping for mentor prompts.

Loads markdown prompt templates from app/prompts/ and interpolates
user context (profile, skill, summary blocks) into placeholders.
"""

import re
from pathlib import Path
from typing import Any

from app.models.chat import DEFAULT_TONE, ToneId
from app.services.l1_scope import extract_situations

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# In-memory cache: filename → raw template string
_cache: dict[str, str] = {}

# Mode → template filename mapping
_MODE_TEMPLATES: dict[str, str] = {
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
    # Routed sub-modes for "topic" turns (see mode_router.py). Each is
    # self-contained — no shared universal "always end with a question"
    # suffix, since that used to defeat DIRECT's whole purpose.
    "diagnostic": (
        "You are running a brief DIAGNOSTIC before teaching this topic.\n"
        "- Ask 1-2 targeted questions to gauge the student's actual mastery of "
        "specific subtopics within this topic. Do NOT teach content yet, do "
        "NOT give the full picture up front. This holds even if the user's "
        "profile below says they prefer answer-first explanations — that "
        "preference shapes how you teach once diagnosis is done, it does not "
        "skip diagnosis.\n"
        "- If Relevant Past Sessions below show related experience, let it "
        "inform your first question's difficulty, but still verify — don't "
        "skip diagnosis on assumption.\n"
        "- Use the quick-reply option format for questions with discrete "
        "plausible answers.\n"
        "- Once the user's answer gives you enough signal on one or more "
        "subtopics, call the record_diagnostic_verdict tool with a mastery "
        "estimate (0-100) for just those subtopics — leave out any subtopic "
        "you haven't actually tested — and tell them briefly what you found "
        "before moving into teaching.\n"
        "- Never call record_diagnostic_verdict as your only output. The tool "
        "call is silent to the user — always write the reply text (what you "
        "found, then either the next question or the start of teaching) in "
        "the same turn as the call, not left for a later turn."
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


def _format_learning_context(profile: dict[str, Any], l1_scope: list[dict] | None = None) -> str:
    """Format the user's Facts About You, filtered to what's relevant to the
    current topic when a scope is available.

    `l1_scope` is the topic's cached classify_relevance output (see
    TopicService._ensure_l1_scope) — each entry carries a `verdict` of
    "relevant", "irrelevant", or "uncertain". `l1_scope is None` means it
    was never computed or the last attempt failed — inject everything
    unfiltered, same as before this filtering existed, rather than dropping
    L1 context on a transient failure. A real (possibly empty) `l1_scope`
    list is used as-is, even if every entry is irrelevant — that's the
    filter doing its job, not a failure to fall back from.

    "uncertain" entries are included (not dropped) — an interim policy,
    pending a real "ask the user" resolution flow (not built yet): missing
    a genuinely relevant item silently is worse than including a borderline
    one until that item gets a real answer.
    """
    situations = extract_situations(profile)

    if l1_scope is not None:
        included = {j["situation"] for j in l1_scope if j.get("verdict") != "irrelevant"}
        situations = [s for s in situations if s in included]

    return "; ".join(situations) if situations else "Not specified"


def _format_taught_concepts(taught_concepts: list[str] | None) -> str:
    """Format the topic's accumulated taughtConcepts list (see
    CompactionService._apply_taught_concepts, TS-1) — an L3 episodic memory
    record, scoped to this topic and concept-grained rather than narrative-
    grained. Specific things already taught in this topic, so the mentor
    doesn't re-teach from scratch or contradict what it already said."""
    if not taught_concepts:
        return "(nothing recorded yet)"
    return "\n".join(f"- {c}" for c in taught_concepts)


def _format_style_notes(style_notes: list[dict[str, Any]]) -> str:
    """Format observed StyleNote entries into a readable bullet list."""
    if not style_notes:
        return "(none observed yet)"
    return "\n".join(
        f"- [{note.get('category', 'context')}] {note.get('note', '')}"
        for note in style_notes
    )


def _format_summary_blocks(blocks: list[dict[str, Any]] | None) -> str:
    """Format this topic's own SummaryBlocks (session-narrative-summary spec),
    oldest first (Requirement 7.2), full text, not truncated (Requirement
    7.1) — this topic's sole narrative L3 source."""
    if not blocks:
        return "(no prior sessions in this topic yet)"
    ordered = sorted(blocks, key=lambda b: b.get("createdAt"))
    return "\n\n".join(b.get("text", "") for b in ordered)


def _format_subtopic_mastery(subtopic_mastery: dict[str, float] | None) -> str:
    """Format the topic's per-subtopic mastery map (see
    .kiro/specs/skill-graph-subtopic-mastery) — replaces the old single
    current_level word with a per-subtopic breakdown, sorted weakest first
    so the mentor sees what needs attention up top."""
    if not subtopic_mastery:
        return "(not assessed yet)"
    ordered = sorted(subtopic_mastery.items(), key=lambda kv: kv[1])
    return "\n".join(f"- {name}: {mastery:.0f}%" for name, mastery in ordered)


def _build_context_variables(
    context: dict[str, Any], mode: str, tone: ToneId
) -> dict[str, str]:
    """Extract template variables from the assembled context dict."""
    profile = context.get("profile", {})
    skill = context.get("skill", {})

    mode_instructions = _MODE_INSTRUCTIONS.get(mode, "")

    return {
        # L1 Profile fields
        "learning_context": _format_learning_context(profile, context.get("l1_scope")),
        # Observed teaching-style notes, grounded per-session (issue #14 evolution)
        "style_notes": _format_style_notes(profile.get("style_notes") or []),
        # L2 Skill fields
        "topic": skill.get("topic", context.get("topic", "General")),
        "subtopic_mastery": _format_subtopic_mastery(skill.get("subtopic_mastery")),
        # L3 Episodic memory
        "taught_concepts": _format_taught_concepts(context.get("taught_concepts")),
        "session_summaries": _format_summary_blocks(context.get("summary_blocks")),
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
        mode: A routed topic sub-mode from mode_router.py ("diagnostic",
            "direct", "socratic", "hint", "guided").
        context: Dict with keys "profile", "skill", "summary_blocks" from context_assembler.
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
