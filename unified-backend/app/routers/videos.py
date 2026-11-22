"""Videos router: add a YouTube video's transcript to a topic's knowledge.

POST starts a background ingest job and returns at once; the frontend
polls GET /api/videos/{video_id} for `status` until it is "completed" or
"failed". See app/services/video_ingest.py for the pipeline.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import require_auth
from app.services.topic_service import TopicService
from app.services.video_ingest import (
    create_video_job,
    delete_video,
    get_video,
    list_topic_videos,
    run_video_ingest,
)
from app.services.youtube_transcript import parse_video_id

router = APIRouter(prefix="/api", tags=["Videos"])

_topic_service = TopicService()
_IN_PROGRESS = {"queued", "fetching", "embedding", "summarizing"}


class AddVideoRequest(BaseModel):
    url: str


@router.post("/topic/{topic_id}/video", status_code=202)
async def add_topic_video(
    topic_id: str,
    body: AddVideoRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_auth),
):
    """Fetch, chunk and embed a YouTube video's full transcript for this topic."""
    await _topic_service.get_topic(topic_id, user_id)

    video_id = parse_video_id(body.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Not a valid YouTube video URL")

    existing = await get_video(user_id, video_id)
    if existing and existing.get("status") in _IN_PROGRESS:
        raise HTTPException(status_code=409, detail="This video is already being processed")

    video = await create_video_job(user_id, topic_id, video_id)
    background_tasks.add_task(run_video_ingest, user_id, topic_id, video_id)
    return {"video": video}


@router.get("/topic/{topic_id}/videos")
async def get_topic_videos(topic_id: str, user_id: str = Depends(require_auth)):
    await _topic_service.get_topic(topic_id, user_id)
    return {"videos": await list_topic_videos(user_id, topic_id)}


@router.get("/videos/{video_id}")
async def get_video_status(video_id: str, user_id: str = Depends(require_auth)):
    video = await get_video(user_id, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"video": video}


@router.delete("/videos/{video_id}")
async def remove_video(video_id: str, user_id: str = Depends(require_auth)):
    """Remove the video, all its transcript chunks and its memory summary."""
    if not await delete_video(user_id, video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    return {"ok": True}
