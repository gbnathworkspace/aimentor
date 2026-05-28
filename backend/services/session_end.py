from datetime import datetime
from core.database import get_collection
from core.models import SkillNode, SkillSignals
from llm.chains import generate_session_end, generate_title
from memory.layer2 import upsert_skill_node
from memory.layer3 import store_summary


async def finalize_session(session_id: str, user_id: str) -> dict:
    sessions_col = get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id, "user_id": user_id})
    if not session:
        raise ValueError(f"Session {session_id} not found")

    transcript = session.get("transcript", [])
    if not transcript:
        return {"status": "skipped", "reason": "empty transcript"}

    output = generate_session_end(transcript)
    title = generate_title(output.narrative_summary)

    await store_summary(
        summary=output.narrative_summary,
        metadata={
            "session_id": session_id,
            "user_id": user_id,
            "topic": session.get("topic"),
            "topic_category": session.get("topic_category"),
            "type": session.get("mode", "topic_session"),
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
        },
    )

    su = output.skill_update
    existing_nodes = await get_collection("skill_graph").find_one(
        {"user_id": user_id, "topic": su.topic}
    )
    existing_signals = existing_nodes.get("signals", {}) if existing_nodes else {}

    node = SkillNode(
        user_id=user_id,
        topic=su.topic,
        current_level=su.current_level,
        required_level=existing_nodes.get("required_level", "medium") if existing_nodes else "medium",
        last_studied=su.last_studied,
        signals=SkillSignals(
            leetcode_solved=existing_signals.get("leetcode_solved", {}),
            mentor_eval_score=su.mock_score,
            weak_areas=su.weak_areas,
            strong_areas=su.strong_areas,
        ),
    )
    await upsert_skill_node(node)

    await sessions_col.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "ended_at": datetime.utcnow(),
                "title": title,
                "summary": output.narrative_summary,
                "skill_update": su.model_dump(),
            }
        },
    )

    return {"status": "ok", "title": title, "skill_update": su.model_dump()}
