"""TopicChatService — orchestrates per-turn LLM calls within topic threads.

Replaces the standalone session model's per-turn flow. Messages are now
appended to a topic thread, context is assembled including SummaryBlocks,
and compaction is checked after each assistant response.

The mentor call streams tokens back to the client (issue: 2-10s perceived
latency) and can loop up to one extra round if the model reaches for
get_skill_detail / get_more_past_sessions before answering (issue: agentic
context pull). See design_decisions/15_llm_orchestration.md for why
LangChain stays here specifically (raw SDK everywhere else).

Requirements: 4.3, 4.4, 4.5, 4.6, 6.4, 14.1
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi.responses import StreamingResponse
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.config.settings import get_settings
from app.models.session import SessionSkillUpdate
from app.services import context_assembler, mode_router, skill_graph_repo
from app.services.compaction_service import CompactionService
from app.services.prompt_store import get_system_prompt
from app.services.response_parsing import extract_suggestions
from app.services.token_counter import OVER_CAPACITY_THRESHOLD, TokenCounter
from app.services.topic_service import TopicService

logger = logging.getLogger(__name__)

# Covers up to 2 sequential model round trips (tool-loop turn) plus the tool
# execution between them. Most turns are a single round and finish well
# under this.
LLM_TIMEOUT_SECONDS = 50

# ponytail: flat cap on searches-per-turn, cost control until usage data justifies
# a per-mode or per-user budget.
WEB_SEARCH_MAX_USES = 3

_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_SEARCH_MAX_USES}

# Bound onto the mentor call only in DIAGNOSTIC mode. tool_choice stays
# "auto" (not forced) so the same response can carry both the reply text
# and — once there's enough signal — this verdict, in one LLM call instead
# of a separate diagnostic-agent round trip. Never treated as a loop tool:
# calling it always ends the turn, same as before streaming/looping existed.
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

# --- Loop tools: the model can call these mid-turn, see the result, and keep
# reasoning before its final reply. Both reuse data the backend already
# fetches — no new DB infra. Real semantic search over episodic memory is
# out of scope (no Atlas vector index exists yet).

_GET_SKILL_DETAIL_TOOL = {
    "name": "get_skill_detail",
    "description": (
        "Look up the user's current level, gap, and weak/strong areas for a "
        "topic OTHER than the one currently being discussed. Use this when "
        "the conversation references another topic's skill state that "
        "isn't already in your context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    },
}

_GET_MORE_EPISODES_TOOL = {
    "name": "get_more_past_sessions",
    "description": (
        "Fetch additional past-session summaries beyond the ones already "
        "shown in Relevant Past Sessions. Use this when the user references "
        "history that isn't covered there."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Optional: filter to a specific topic."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    },
}

_LOOP_TOOL_NAMES = {_GET_SKILL_DETAIL_TOOL["name"], _GET_MORE_EPISODES_TOOL["name"]}

# One tool-decision round, then one forced-final-answer round. Keeps worst
# case latency to 2 model calls instead of unbounded looping.
_MAX_LOOP_ROUNDS = 2

# Held-back trailing window so a streamed ```json suggestions fence is never
# shown to the client raw before it's stripped. The model doesn't always put
# the fence last (it may keep talking after it), so this alone isn't enough —
# see _FENCE_START below, which additionally pins the flush point to wherever
# an opening fence appears, however far back that is.
_STREAM_TRAIL_BUFFER = 200

# Opening delimiter of the suggestions fence (matches response_parsing.py's
# _SUGGESTIONS_RE). Once this appears in the pending buffer, nothing from
# that point on is flushed until the fence is stripped at stream end —
# regardless of how much more text the model emits after it.
_FENCE_START = "```json suggestions"

# Sentinel separating the visible reply from trailing {mode, suggestions}
# metadata that can't ride on headers (streaming has already started, 200
# already sent) — same trick as mentor.py's in-band error marker, carrying
# structured data instead of an error string.
_META_MARKER = "\x00META\x00"

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
    5. Stream the LLM reply (via ChatAnthropic), looping once if the model
       reaches for get_skill_detail / get_more_past_sessions
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
    ) -> dict | StreamingResponse:
        """Handle a user message within a topic thread.

        Args:
            topic_id: The topic identifier.
            user_id: The authenticated user's ID.
            content: The user's message text.
            mode: Chat mode (topic/planning/doubt/evaluation).

        Returns:
            A dict with an "error" key if the turn is rejected before any
            LLM call (capacity cap), or a StreamingResponse of plain-text
            chunks ending with a `_META_MARKER` + JSON {mode, suggestions}
            trailer on success.
        """
        # Step 0: Hard cap — reject before an LLM call is made or the user
        # message is even accepted, once the topic is at capacity. Compaction
        # (post-turn hook below) is best-effort and async — it can keep
        # failing turn after turn with nothing to stop the topic from growing,
        # so this is the actual backstop on topic size. Runs before any bytes
        # are streamed, so a normal JSON error response is still possible here.
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

        # Step 3: Assemble L1/L2/L3 context (Req 4.3). Raises HTTPException(400)
        # if no profile — still surfaces as a normal error response since
        # nothing has streamed yet.
        context = await context_assembler.assemble(
            user_id, topic_title, content,
            l1_scope=topic.get("l1_scope"), taught_concepts=topic.get("taughtConcepts"),
        )

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
        total_messages = len(messages) + 1  # +1 for the assistant turn about to be appended

        return StreamingResponse(
            self._stream_turn(
                topic_id=topic_id,
                user_id=user_id,
                topic_title=topic_title,
                system_prompt=system_prompt,
                messages=messages,
                include_diagnostic_tool=include_diagnostic_tool,
                effective_mode=effective_mode,
                context=context,
                total_messages=total_messages,
            ),
            media_type="text/plain; charset=utf-8",
        )

    async def _stream_turn(
        self,
        topic_id: str,
        user_id: str,
        topic_title: str,
        system_prompt: str,
        messages: list[dict],
        include_diagnostic_tool: bool,
        effective_mode: str,
        context: dict,
        total_messages: int,
    ):
        """Run the tool-loop mentor call, streaming text as it's generated.

        On success: streams the reply (suggestions fence held back and
        stripped), persists the assistant message, applies any diagnostic
        verdict, fires the post-turn hook, then yields a trailing
        `_META_MARKER` + JSON {mode, suggestions}.
        On failure: yields an in-band error marker, matching mentor.py's
        convention — the stream has already started (200 sent), so a status
        code can't change; the user message is preserved either way (Req 4.4).
        """
        full_text = ""
        pending = ""  # trailing buffer withheld from the client
        final_tool_calls: list[dict] = []
        start = time.monotonic()

        try:
            lc_messages = self._to_langchain_messages(system_prompt, messages)
            tools = [_WEB_SEARCH_TOOL, _GET_SKILL_DETAIL_TOOL, _GET_MORE_EPISODES_TOOL]
            if include_diagnostic_tool:
                tools.append(_DIAGNOSTIC_VERDICT_TOOL)

            for round_idx in range(_MAX_LOOP_ROUNDS):
                round_tools = tools
                if round_idx == _MAX_LOOP_ROUNDS - 1:
                    # Final round: strip loop tools so the model is forced to
                    # answer instead of asking for more.
                    round_tools = [t for t in tools if t["name"] not in _LOOP_TOOL_NAMES]

                llm = ChatAnthropic(
                    model="claude-sonnet-5",
                    max_tokens=8192,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "high"},
                    api_key=get_settings().ANTHROPIC_API_KEY,
                ).bind_tools(round_tools, tool_choice="auto")

                accumulated = None
                async for chunk in llm.astream(lc_messages):
                    if time.monotonic() - start > LLM_TIMEOUT_SECONDS:
                        raise TimeoutError("mentor stream exceeded time budget")
                    accumulated = chunk if accumulated is None else accumulated + chunk
                    for block in self._text_blocks(chunk.content):
                        full_text += block
                        pending += block
                        fence_pos = pending.find(_FENCE_START)
                        flush_len = fence_pos if fence_pos != -1 else len(pending) - _STREAM_TRAIL_BUFFER
                        if flush_len > 0:
                            yield pending[:flush_len]
                            pending = pending[flush_len:]

                tool_calls = accumulated.tool_calls if accumulated else []
                loop_calls = [tc for tc in tool_calls if tc["name"] in _LOOP_TOOL_NAMES]

                if not loop_calls or round_idx == _MAX_LOOP_ROUNDS - 1:
                    final_tool_calls = tool_calls
                    break

                # Execute the requested lookups locally, feed results back,
                # and continue to the next round for the real answer.
                lc_messages.append(accumulated)
                for tc in loop_calls:
                    result_text = await self._execute_loop_tool(
                        tc["name"], tc.get("args") or {}, user_id, context
                    )
                    lc_messages.append(ToolMessage(content=result_text, tool_call_id=tc["id"]))

        except Exception:
            logger.exception(
                "Mentor stream failed for topic=%s user=%s mode=%s",
                topic_id, user_id, effective_mode,
            )
            yield "\n\n[error: the mentor response was interrupted — please try again]"
            return

        # Diagnostic verdict write-back (Req: flips assessed=True so the
        # cold-start gate stops firing on the next message).
        if include_diagnostic_tool:
            await self._apply_diagnostic_verdict(final_tool_calls, user_id, topic_title)

        # Strip the suggestions fence out of the visible text before
        # persisting, then flush whatever clean tail wasn't shown yet.
        clean_content, suggestions = extract_suggestions(full_text)
        already_shown_len = len(full_text) - len(pending)
        remaining = clean_content[already_shown_len:] if already_shown_len < len(clean_content) else ""
        if remaining:
            yield remaining

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

        asyncio.create_task(self._post_turn_hook(topic_id, user_id, total_messages))

        yield _META_MARKER + json.dumps({"mode": effective_mode, "suggestions": suggestions})

    @staticmethod
    def _text_blocks(content) -> list[str]:
        """Extract visible text pieces from a streamed content delta.

        `thinking` blocks are intentionally skipped — extended thinking stays
        internal, only "text" blocks are shown to the user (matches the
        non-streaming extraction this replaces).
        """
        if isinstance(content, str):
            return [content] if content else []
        if not isinstance(content, list):
            return []
        return [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ]

    async def _execute_loop_tool(
        self, name: str, tool_input: dict, user_id: str, context: dict
    ) -> str:
        """Run a loop tool locally and return its result as plain text for
        the model. Fail-open on any error — matches context_assembler.py's
        pattern, a lookup miss shouldn't break the turn."""
        try:
            if name == "get_skill_detail":
                return self._format_skill_detail(tool_input.get("topic", ""), context)
            if name == "get_more_past_sessions":
                topic = tool_input.get("topic") or None
                limit = min(max(int(tool_input.get("limit") or 5), 1), 10)
                episodes = await context_assembler.fetch_additional_episodes(user_id, topic, limit)
                if not episodes:
                    return "No additional past sessions found."
                return "\n\n".join(
                    f"[{e.get('title', 'Untitled session')}] {e.get('summary', '')}"
                    for e in episodes
                )
            return f"Unknown tool: {name}"
        except Exception as e:
            logger.warning("Loop tool %s failed for user=%s: %s", name, user_id, e)
            return f"Lookup failed for {name} — proceed without this information."

    @staticmethod
    def _format_skill_detail(topic: str, context: dict) -> str:
        node = next(
            (
                n for n in context.get("skill_graph") or []
                if str(n.get("topic", "")).lower() == topic.lower()
            ),
            None,
        )
        if not node:
            return f"No skill data found for topic '{topic}'."
        return (
            f"Topic: {node.get('topic')}\n"
            f"Current level: {node.get('current_level', 'not assessed')}\n"
            f"Required level: {node.get('required_level', 'unknown')}\n"
            f"Gap: {node.get('gap', 'unknown')}\n"
            f"Weak areas: {', '.join(node.get('weak_areas') or []) or 'none recorded'}\n"
            f"Strong areas: {', '.join(node.get('strong_areas') or []) or 'none recorded'}"
        )

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
        self, tool_calls: list[dict], user_id: str, topic_title: str
    ) -> None:
        """If the mentor called record_diagnostic_verdict this turn, write it
        to the skill graph. Best-effort: a failure here shouldn't break the
        turn — the periodic skill checkpoint (extract_skill_updates_only)
        is the backstop if this write is lost.
        """
        verdict = next(
            (tc for tc in tool_calls if tc["name"] == "record_diagnostic_verdict"),
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
