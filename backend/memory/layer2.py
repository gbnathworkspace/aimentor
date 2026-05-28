from core.database import get_collection
from core.models import SkillNode


async def get_skill_graph(user_id: str, topic: str | None = None) -> list[dict]:
    col = get_collection("skill_graph")
    query: dict = {"user_id": user_id}
    if topic:
        query["topic"] = topic
    cursor = col.find(query, {"_id": 0}).sort("gap", -1)
    return await cursor.to_list(length=20)


async def upsert_skill_node(node: SkillNode) -> None:
    col = get_collection("skill_graph")
    await col.update_one(
        {"user_id": node.user_id, "topic": node.topic},
        {"$set": node.model_dump()},
        upsert=True,
    )


def format_for_context(nodes: list[dict]) -> str:
    if not nodes:
        return "No skill graph data yet."
    lines = ["Topic skill gaps (sorted by gap, largest first):"]
    for n in nodes[:6]:
        lines.append(
            f"- {n['topic']}: current={n.get('current_level','?')} "
            f"required={n.get('required_level','?')} gap={n.get('gap','?')}"
        )
    return "\n".join(lines)
