from memory import layer1, layer2, layer3
from llm.chains import check_intent_needs_context
from llm.prompts import MENTOR_SYSTEM_PROMPT, GOAL_ANCHOR_TEMPLATE


async def assemble(
    user_id: str,
    message: str,
    topic: str | None = None,
    topic_category: str | None = None,
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """
    Returns (system_prompt, messages_list) ready for Claude.
    system_prompt = mentor persona + L1 + L2 + L3 (if needed) + goal anchor
    messages_list = conversation history + current user message
    """
    profile = await layer1.get_profile(user_id)
    skill_nodes = await layer2.get_skill_graph(user_id, topic)

    l1_text = layer1.format_for_context(profile) if profile else "No profile yet."
    l2_text = layer2.format_for_context(skill_nodes)

    needs_episodic = check_intent_needs_context(message)
    l3_text = ""
    if needs_episodic:
        summaries = await layer3.retrieve_relevant(message, topic_category)
        l3_text = layer3.format_for_context(summaries)

    top_gap = skill_nodes[0]["topic"] if skill_nodes else "unknown"
    goal = profile.get("goal", "your goal") if profile else "your goal"
    deadline = profile.get("deadline", "your deadline") if profile else "your deadline"

    goal_anchor = GOAL_ANCHOR_TEMPLATE.format(
        goal=goal,
        deadline=deadline,
        top_gap=f"{top_gap} (gap: {skill_nodes[0].get('gap', '?')})" if skill_nodes else top_gap,
    )

    system_parts = [MENTOR_SYSTEM_PROMPT, "\n\n## User Context\n", l1_text, "\n\n## Skill Graph\n", l2_text]
    if l3_text:
        system_parts.extend(["\n\n## Relevant Past Sessions\n", l3_text])
    system_parts.append(goal_anchor)

    system_prompt = "".join(system_parts)

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": message})

    return system_prompt, messages
