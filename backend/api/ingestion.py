from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pipeline.ingestion import process_resume, process_leetcode_csv
from memory.layer1 import upsert_profile, get_profile
from memory.layer2 import get_skill_graph, upsert_skill_node
from core.models import CoreProfile, SkillNode, SkillSignals

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    content = await file.read()
    parsed = await process_resume(content, file.filename, user_id)
    return {"status": "ok", "parsed": parsed}


@router.post("/leetcode")
async def upload_leetcode(
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    content = await file.read()
    result = await process_leetcode_csv(content, user_id)

    skill_nodes = await get_skill_graph(user_id)
    for node_doc in skill_nodes:
        node = SkillNode(
            user_id=user_id,
            topic=node_doc["topic"],
            current_level=node_doc.get("current_level", "unknown"),
            required_level=node_doc.get("required_level", "medium"),
            signals=SkillSignals(
                leetcode_solved=result["leetcode_solved"],
                weak_areas=node_doc.get("signals", {}).get("weak_areas", []),
                strong_areas=node_doc.get("signals", {}).get("strong_areas", []),
            ),
        )
        await upsert_skill_node(node)

    return {"status": "ok", "leetcode_signals": result}
