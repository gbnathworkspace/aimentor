"""TopicChatService — orchestrates per-turn LLM calls within topic threads.

Replaces the standalone session model's per-turn flow. Messages are now
appended to a topic thread, context is assembled including SummaryBlocks,
and compaction is checked after each assistant response.

Requirements: 4.3, 4.4, 4.5, 4.6, 6.4, 14.1
"""

import asyncio
import logging
import uuid
from datetime import datetime

import anthropic

from app.config.settings import get_settings
from app.services import context_assembler
from app.services.compaction_service import CompactionService
from app.services.prompt_store import get_system_prompt
from app.services.response_parsing import extract_suggestions
from app.services.token_counter import TokenCounter
from app.services.topic_service import TopicService

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 30

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
        now = datetime.utcnow()

        # Step 1: Create and append user message (Req 4.1)
        user_msg = {
            "type": "message",
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": content,
            "timestamp": now,
        }

        await self._topic_service.append_message(topic_id, user_id, user_msg)

        # Step 2: Get topic data for context assembly
        topic = await self._topic_service.get_topic(topic_id, user_id)
        messages = topic.get("messages", [])
        topic_title = topic.get("title", "General")

        # Step 3: Assemble L1/L2/L3 context (Req 4.3)
        context = await context_assembler.assemble(user_id, topic_title, content)

        # Step 4: Build system prompt
        system_prompt = get_system_prompt(mode, context)

        # Step 5: Call LLM with 30s timeout (Req 4.3)
        try:
            assistant_content = await asyncio.wait_for(
                self._call_llm(system_prompt, messages),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            # Req 4.4: retain user message (already appended), return error
            logger.error("LLM call failed for topic %s: %s", topic_id, str(e))
            return {
                "error": "The assistant response could not be generated. Please try again."
            }

        # Step 5b: Strip any quick-reply suggestions block out of the visible text
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
            "timestamp": datetime.utcnow(),
            "systemPrompt": system_prompt,
        }
        await self._topic_service.append_message(topic_id, user_id, assistant_msg)

        # Step 7: Post-turn hook — async compaction / skill-checkpoint check (Req 6.4, 14.1)
        total_messages = len(messages) + 1  # messages already includes the user turn
        asyncio.create_task(self._post_turn_hook(topic_id, user_id, total_messages))

        return {"response": clean_content, "suggestions": suggestions}

    async def _call_llm(self, system_prompt: str, messages: list[dict]) -> str:
        """Call Anthropic Claude with the assembled context.

        Converts topic messages (including SummaryBlocks) into the format
        expected by the Anthropic API.

        Returns the assistant's response text.
        """
        settings = get_settings()
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Convert messages to Anthropic format
        api_messages = self._format_messages_for_api(messages)

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=api_messages,
        )

        return response.content[0].text

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
