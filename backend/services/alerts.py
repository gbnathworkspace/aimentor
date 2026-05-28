import anthropic
import json
from datetime import datetime, timedelta
from core.config import settings
from core.database import get_collection
from memory.layer1 import get_profile
from memory.layer2 import get_skill_graph

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

ALERT_PROMPT = """Here is a user's goal, deadline, skill graph, and last activity dates.
Is there anything worth flagging today? If yes, produce one concise alert.
If no, return null.

Return ONLY valid JSON: {{"alert": "..." }} or {{"alert": null}}

User context:
{context}"""


async def run_daily_alert(user_id: str) -> dict | None:
    profile = await get_profile(user_id)
    if not profile:
        return None

    skill_nodes = await get_skill_graph(user_id)
    users_col = get_collection("users")
    user_doc = await users_col.find_one({"user_id": user_id})

    last_sent = user_doc.get("last_email_sent") if user_doc else None
    if last_sent and (datetime.utcnow() - last_sent) < timedelta(hours=24):
        return None

    context = f"Goal: {profile.get('goal')}\nDeadline: {profile.get('deadline')}\n"
    context += "Skill gaps:\n"
    for node in skill_nodes[:5]:
        context += f"  - {node['topic']}: gap={node.get('gap')} last_studied={node.get('last_studied')}\n"

    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": ALERT_PROMPT.format(context=context)}],
    )
    data = json.loads(response.content[0].text.strip())
    return data.get("alert")
