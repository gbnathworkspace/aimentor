"""TopicChatService — orchestrates per-turn LLM calls within topic threads.

Replaces the standalone session model's per-turn flow. Messages are now
appended to a topic thread, context is assembled including SummaryBlocks,
and compaction is checked after each assistant response.

Requirements: 4.3, 4.4, 4.5, 4.6, 6.4, 14.1
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config.settings import get_settings
from app.models.session import SessionSkillUpdate
from app.services import context_assembler, mode_router, skill_graph_repo
from app.services.compaction_service import CompactionService
from app.services.prompt_store import get_system_prompt
from app.services.response_parsing import extract_suggestions
from app.services.token_counter import OVER_CAPACITY_THRESHOLD, TokenCounter
from app.services.topic_service import TopicService

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 45  # web search adds a server-side fetch round trip

# ponytail: flat cap on searches-per-turn, cost control until usage data justifies
# a per-mode or per-user budget.
WEB_SEARCH_MAX_USES = 3

_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES}

# Bound onto the mentor call only in DIAGNOSTIC mode. tool_choice stays
# "auto" (not forced) so the same response can carry both the reply text
# and — once there's enough signal — this verdict, in one LLM call instead
# of a separate diagnostic-agent round trip.
_DIAGNOSTIC_VERDICT_TOOL = {
    "name": "record_diagnostic_verdict",
    "description": (
        "Record the assessed skill level once the user's answer gives enough "
        "signal to judge it. Do not call this until you're confident — it's "
        "fine to ask another question first and call it on a later turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "new_level": {
                "type": "string",
                "enum": ["beginner", "intermediate", "advanced", "expert"],
            },
            "gap": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Estimated gap to required proficiency: 0 = none, 100 = huge.",
            },
            "weak_areas": {"type": "array", "items": {"type": "string"}},
            "strong_areas": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["new_level", "gap", "weak_areas", "strong_areas"],
    },
}

# Compaction only extracts skill updates as a side effect of reclaiming context
# space — a topic that never grows big enough to compact never touches the skill
# graph. This runs a lightweight skill-only check every N messages regardless.
# ponytail: cadence is total-array-length modulo, which drifts after compaction
# shrinks the array (a summary block collapses many messages into one) — good
# enough for a periodic progress signal, not a precise per-turn counter.
SKILL_CHECK_EVERY_N_MESSAGES = 16  # 8 user+assistant exchanges


class TopicChatService:
    """Orchestrates per-turn LLM calls within topic threads.

    Flow:
    1. User sends a message within a topic
    2. Append user message to topic thread (via TopicService)
    3. Get all messages from topic (including SummaryBlocks)
    4. Assemble context (L1/L2/L3 via existing context_assembler)
    5. Call the LLM (via Anthropic client)
    6. Append assistant response to topic thread
    7. Post-turn hook: check if compaction needed, trigger async if so
    """

    def __init__(
        self,
        topic_service: TopicService | None = None,
        compaction_service: CompactionService | None = None,
        token_counter: TokenCounter | None = None,
    ):
        self._topic_service = topic_service or TopicService()
        self._compaction_service = compaction_service or CompactionService()
        self._token_counter = token_counter or TokenCounter()

    async def handle_message(
        self, topic_id: str, user_id: str, content: str, mode: str = "topic"
    ) -> dict:
        """Handle a user message within a topic thread.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            content: The user's message text.
            mode: Chat mode (topic/planning/doubt/evaluation).

        Returns:
            Dict with "response" (assistant content) on success,
            or "error" key on failure.
        """
        # Step 0: Hard cap — reject before an LLM call is made or the user
        # message is even accepted, once the topic is at capacity. Compaction
        # (post-turn hook below) is best-effort and async — it can keep
        # failing turn after turn with nothing to stop the topic from growing,
        # so this is the actual backstop on topic size.
        topic = await self._topic_service.get_topic(topic_id, user_id)
        existing_messages = topic.get("messages", [])
        topic_title = topic.get("title", "General")
        if self._token_counter.get_usage_percent(existing_messages) >= OVER_CAPACITY_THRESHOLD:
            return {
                "error": "This topic has reached its size limit. Start a new topic to continue.",
                "topicFull": True,
            }

        now = datetime.now(timezone.utc)

        # Step 1: Create and append user message (Req 4.1)
        user_msg = {
            "type": "message",
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": content,
            "timestamp": now,
        }

        await self._topic_service.append_message(topic_id, user_id, user_msg)

        # Step 2: Build the message list for context assembly — reuse the
        # pre-append fetch above instead of a second DB round trip.
        messages = existing_messages + [user_msg]

        # Step 3: Assemble L1/L2/L3 context (Req 4.3)
        context = await context_assembler.assemble(user_id, topic_title, content)

        # Step 3b: Route "topic" turns to a specific teaching tactic instead of
        # one static block that used to give contradictory instructions (probe
        # first vs explain first vs attempt-first, all at once, no priority).
        # doubt/planning/evaluation are untouched — they're session-level
        # intents, not per-message tactics.
        effective_mode = mode
        instruction_override = ""
        if mode == "topic":
            decision = await mode_router.route_user_turn(
                query=content,
                skill=context.get("skill") or {},
                recent_messages=existing_messages,
                profile=context.get("profile"),
            )
            effective_mode = decision.selected_mode.value.lower()
            instruction_override = decision.instruction_override

        # Step 4: Build system prompt
        system_prompt = get_system_prompt(effective_mode, context)
        if instruction_override:
            system_prompt += f"\n\n## This Turn's Specific Instruction\n{instruction_override}"

        include_diagnostic_tool = effective_mode == "diagnostic"

        # Step 5: Call LLM with 30s timeout (Req 4.3)
        try:
            ai_message = await asyncio.wait_for(
                self._call_llm(system_prompt, messages, include_diagnostic_tool),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            # Req 4.4: retain user message (already appended), return error
            logger.error("LLM call failed for topic %s: %s", topic_id, str(e))
            return {
                "error": "The assistant response could not be generated. Please try again."
            }

        assistant_content = "".join(
            block.get("text", "")
            for block in ai_message.content
            if isinstance(block, dict) and block.get("type") == "text"
        )

        # Step 5b: If the mentor recorded a diagnostic verdict this turn, write
        # it to the skill graph now — this is what flips assessed=True and
        # stops the diagnostic gate from firing on the next message.
        if include_diagnostic_tool:
            await self._apply_diagnostic_verdict(ai_message, user_id, topic_title)

        # Step 5c: Strip any quick-reply suggestions block out of the visible text
        # before persisting — the stored history (and future LLM calls) should
        # never see the raw JSON fence.
        clean_content, suggestions = extract_suggestions(assistant_content)

        # Step 6: Append assistant message (Req 4.5)
        # systemPrompt records the exact L1/L2/L3-assembled prompt sent for this
        # turn — context (profile/skill/episodes) changes over time, so this is
        # only reconstructable historically if stored per-turn, not on demand.
        assistant_msg = {
            "type": "message",
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": clean_content,
            "timestamp": datetime.now(timezone.utc),
            "systemPrompt": system_prompt,
            "mode": effective_mode,
        }
        await self._topic_service.append_message(topic_id, user_id, assistant_msg)

        # Step 7: Post-turn hook — async compaction / skill-checkpoint check (Req 6.4, 14.1)
        total_messages = len(messages) + 1  # messages already includes the user turn
        asyncio.create_task(self._post_turn_hook(topic_id, user_id, total_messages))

        return {"response": clean_content, "suggestions": suggestions, "mode": effective_mode}

    async def _call_llm(
        self, system_prompt: str, messages: list[dict], include_diagnostic_tool: bool
    ) -> AIMessage:
        """Call Claude (via LangChain) with the assembled context.

        Converts topic messages (including SummaryBlocks) into LangChain
        message objects. Returns the raw AIMessage — callers read `.content`
        for reply text and `.tool_calls` for any tool invocations (verified
        against a live call: cache_control blocks, adaptive thinking, and
        output_config effort=high all pass through langchain-anthropic
        unchanged; tool_choice="auto" returns text and a tool call in the
        same response when the model has both).
        """
        settings = get_settings()
        llm = ChatAnthropic(
            model="claude-sonnet-5",
            # ponytail: 4096 was too tight for diagram-heavy replies — adaptive
            # thinking shares this budget with output, and an SVG diagram plus
            # explanation can get cut mid-<svg> tag, rendering as a mostly-empty
            # block (truncated canvas size, only trailing shapes drawn).
            max_tokens=8192,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            api_key=settings.ANTHROPIC_API_KEY,
        )

        tools = [_WEB_SEARCH_TOOL]
        if include_diagnostic_tool:
            tools.append(_DIAGNOSTIC_VERDICT_TOOL)

        # tool_choice stays "auto" (not forced) — DIAGNOSTIC-mode turns need to
        # ask a question with no tool call at all until there's enough signal.
        bound = llm.bind_tools(tools, tool_choice="auto")

        return await bound.ainvoke(self._to_langchain_messages(system_prompt, messages))

    def _to_langchain_messages(self, system_prompt: str, messages: list[dict]) -> list:
        """Convert the assembled system prompt + topic messages into LangChain
        message objects, reusing the existing cache-block and role-mapping
        logic unchanged."""
        api_messages = self._format_messages_for_api(messages)
        lc_messages: list = [SystemMessage(content=self._build_system_blocks(system_prompt))]
        for m in api_messages:
            msg_cls = HumanMessage if m["role"] == "user" else AIMessage
            lc_messages.append(msg_cls(content=m["content"]))
        return lc_messages

    async def _apply_diagnostic_verdict(
        self, ai_message: AIMessage, user_id: str, topic_title: str
    ) -> None:
        """If the mentor called record_diagnostic_verdict this turn, write it
        to the skill graph. Best-effort: a failure here shouldn't break the
        turn — the periodic skill checkpoint (extract_skill_updates_only)
        is the backstop if this write is lost.
        """
        verdict = next(
            (tc for tc in ai_message.tool_calls if tc["name"] == "record_diagnostic_verdict"),
            None,
        )
        if not verdict:
            return

        try:
            skill_update = SessionSkillUpdate(topic=topic_title, **verdict["args"])
            await skill_graph_repo.apply_update(user_id, skill_update)
        except Exception as e:
            logger.warning(
                "Diagnostic verdict write failed for topic=%s user=%s: %s",
                topic_title,
                user_id,
                str(e),
            )

    def _build_system_blocks(self, system_prompt: str) -> list[dict]:
        """Split the system prompt into three cache blocks, most-stable first,
        so a change to one doesn't blow away the cache for the others (issue #23):

        1. Static instructions (never changes — deployment-constant, cacheable
           across every user/topic, not just this one)
        2. L1 profile + teaching prefs (changes rarely — onboarding edits)
        3. L2 skill graph + L3 episodes + documents + mode/tone (changes often
           — every ~16 messages or on compaction; left uncacheable-on-its-own
           on purpose, no further split — the 4-breakpoint request limit is
           already spent here plus the conversation-history marker)

        mentor_v1.md marks the splits with `<!--STATIC-BOUNDARY-->` and
        `<!--L1-BOUNDARY-->`. Falls back to fewer blocks if a marker is
        missing (e.g. a future template edit drops one).
        """
        static_marker = "<!--STATIC-BOUNDARY-->"
        l1_marker = "<!--L1-BOUNDARY-->"

        remainder = system_prompt
        blocks: list[str] = []

        if static_marker in remainder:
            static_block, remainder = remainder.split(static_marker, 1)
            blocks.append(static_block.rstrip())

        if l1_marker in remainder:
            l1_block, remainder = remainder.split(l1_marker, 1)
            blocks.append(l1_block.strip())

        blocks.append(remainder.lstrip())

        return [
            {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
            for text in blocks
        ]

    def _format_messages_for_api(self, messages: list[dict]) -> list[dict]:
        """Convert topic messages (including SummaryBlocks) to Anthropic API format.

        SummaryBlocks are converted to "assistant" messages with a system note prefix.
        Regular messages are passed through with role and content.
        The result must start with a "user" message (Anthropic requirement).
        """
        api_messages = []

        for msg in messages:
            if msg.get("type") == "summary":
                # SummaryBlocks become a context note in the conversation
                api_messages.append({
                    "role": "assistant",
                    "content": f"[Summary of earlier conversation: {msg.get('summary', '')}]",
                })
            else:
                role = msg.get("role", "user")
                # Normalize "mentor" role to "assistant" for API compatibility
                if role == "mentor":
                    role = "assistant"
                api_messages.append({
                    "role": role,
                    "content": msg.get("content", ""),
                })

        # Ensure first message is from user (Anthropic requirement)
        first_user = next(
            (i for i, m in enumerate(api_messages) if m["role"] == "user"),
            len(api_messages),
        )
        api_messages = api_messages[first_user:]

        # Keep only last 20 messages to avoid context overflow
        if len(api_messages) > 20:
            api_messages = api_messages[-20:]
            # Re-trim to start with user
            first_user = next(
                (i for i, m in enumerate(api_messages) if m["role"] == "user"),
                len(api_messages),
            )
            api_messages = api_messages[first_user:]

        # Cache breakpoint on the last message (the turn just appended). The
        # next call resends this same prefix verbatim, so this lets Anthropic
        # serve it from cache instead of billing full price every turn.
        if api_messages:
            last = api_messages[-1]
            last["content"] = [{
                "type": "text",
                "text": last["content"],
                "cache_control": {"type": "ephemeral"},
            }]

        return api_messages

    async def _post_turn_hook(self, topic_id: str, user_id: str, total_messages: int) -> None:
        """Post-turn compaction / skill-checkpoint check (Req 6.4, 14.1).

        Runs asynchronously after the response is returned to the user. Checks if
        compaction is needed and triggers it if so — compaction already extracts
        skill updates as part of its flow. Otherwise, every SKILL_CHECK_EVERY_N_MESSAGES
        messages, runs a skill-only checkpoint so topics that never grow large enough
        to compact still contribute to the skill graph.
        """
        try:
            should_compact = await self._compaction_service.should_compact(
                topic_id, user_id
            )
            if should_compact:
                await self._compaction_service.compact(topic_id, user_id)
            elif total_messages > 0 and total_messages % SKILL_CHECK_EVERY_N_MESSAGES == 0:
                await self._compaction_service.extract_skill_updates_only(topic_id, user_id)
        except Exception as e:
            logger.error(
                "Post-turn hook failed for topic %s: %s", topic_id, str(e)
            )
