import uuid
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from core.models import ChatRequest, SessionStartRequest, SessionEndRequest, ChatMessage
from core.database import get_collection
from pipeline.context import assemble
from llm.chains import stream_chat
from services.session_end import finalize_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/session/start")
async def start_session(req: SessionStartRequest):
    session_id = str(uuid.uuid4())
    sessions_col = get_collection("sessions")
    await sessions_col.insert_one({
        "session_id": session_id,
        "user_id": req.user_id,
        "created_at": datetime.utcnow(),
        "mode": req.mode,
        "topic": req.topic,
        "topic_category": req.topic_category,
        "transcript": [],
    })
    return {"session_id": session_id}


@router.post("/message")
async def send_message(req: ChatRequest):
    sessions_col = get_collection("sessions")
    session = await sessions_col.find_one({"session_id": req.session_id})
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in (session.get("transcript", []) if session else [])
    ][-12:]  # last 6 turns

    system_prompt, messages = await assemble(
        user_id=req.user_id,
        message=req.message,
        topic=req.topic,
        topic_category=req.topic_category,
        history=history,
    )

    user_msg = ChatMessage(role="user", content=req.message)
    await sessions_col.update_one(
        {"session_id": req.session_id},
        {"$push": {"transcript": user_msg.model_dump()}},
    )

    full_response: list[str] = []

    def generate():
        for chunk in stream_chat(system_prompt, messages):
            full_response.append(chunk)
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    async def save_after_stream():
        response_text = "".join(full_response)
        assistant_msg = ChatMessage(role="assistant", content=response_text)
        await sessions_col.update_one(
            {"session_id": req.session_id},
            {"$push": {"transcript": assistant_msg.model_dump()}},
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/session/end")
async def end_session(req: SessionEndRequest):
    result = await finalize_session(req.session_id, req.user_id)
    return result


@router.get("/sessions/{user_id}")
async def list_sessions(user_id: str):
    sessions_col = get_collection("sessions")
    cursor = sessions_col.find(
        {"user_id": user_id, "ended_at": {"$exists": True}},
        {"_id": 0, "transcript": 0, "embedding": 0},
    ).sort("ended_at", -1).limit(50)
    return await cursor.to_list(length=50)


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    sessions_col = get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id}, {"_id": 0, "embedding": 0})
    return session
