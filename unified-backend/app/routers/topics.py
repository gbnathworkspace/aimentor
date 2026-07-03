"""Topics router — /api/topics and /api/topic/:id CRUD + messaging endpoints.

Provides topic creation, listing, retrieval, renaming, archival, and
per-topic message sending. All routes enforce authenticated userId ownership
and return identical 404 responses for not-found and unauthorized to prevent
topic ID enumeration (Req 15.5).

Requirements: 1.1, 1.2, 1.3, 2.4, 3.1, 3.3, 4.1, 14.4, 15.1, 15.2, 15.3, 15.5
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import require_auth
from app.services.topic_service import TopicService
from app.services.topic_chat_service import TopicChatService

router = APIRouter(prefix="/api", tags=["Topics"])

_topic_service = TopicService()
_chat_service = TopicChatService()


# --- Request/Response Models ---


class CreateTopicRequest(BaseModel):
    """Request body for creating a new topic."""

    title: str = Field(..., min_length=1, max_length=100)


class RenameTopicRequest(BaseModel):
    """Request body for renaming a topic."""

    title: str = Field(..., min_length=1, max_length=100)


class SendMessageRequest(BaseModel):
    """Request body for sending a message within a topic."""

    content: str = Field(..., min_length=1, max_length=50000)
    mode: str = Field(default="topic")


# --- Routes ---


@router.post("/topics")
async def create_topic(body: CreateTopicRequest, user_id: str = Depends(require_auth)):
    """Create a new topic.

    Supports auto-creation from first message by creating the topic with
    the provided title. The client can then immediately POST a message.
    """
    topic = await _topic_service.create_topic(user_id, body.title)
    return topic


@router.get("/topics")
async def list_topics(user_id: str = Depends(require_auth)):
    """List active topics for the authenticated user.

    Returns up to 50 topics ordered by lastActiveAt descending,
    with a message preview from the most recent message.
    """
    topics = await _topic_service.list_topics(user_id)
    return topics


@router.get("/topics/archived")
async def list_archived_topics(user_id: str = Depends(require_auth)):
    """List archived topics for the authenticated user."""
    topics = await _topic_service.list_archived_topics(user_id)
    return topics


@router.get("/topic/{topic_id}")
async def get_topic(topic_id: str, user_id: str = Depends(require_auth)):
    """Get a single topic with ownership check.

    Returns 404 for both not-found and unauthorized access to prevent
    topic ID enumeration.
    """
    topic = await _topic_service.get_topic(topic_id, user_id)
    return topic


@router.get("/topic/{topic_id}/messages")
async def get_messages_paginated(
    topic_id: str,
    user_id: str = Depends(require_auth),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
):
    """Get paginated messages from a topic (Req 14.4).

    Supports lazy loading for large topics (>500 messages).
    Returns the most recent messages first; use 'skip' to load
    older messages on scroll.

    Query params:
        limit: Number of messages to return (1-100, default 50)
        skip: Number of messages to skip from the end (default 0)
    """
    result = await _topic_service.get_messages_paginated(
        topic_id, user_id, limit=limit, skip=skip
    )
    return result


@router.patch("/topic/{topic_id}")
async def rename_topic(
    topic_id: str, body: RenameTopicRequest, user_id: str = Depends(require_auth)
):
    """Rename a topic. Validates title (1-100 chars after trim)."""
    topic = await _topic_service.rename_topic(topic_id, user_id, body.title)
    return topic


@router.post("/topic/{topic_id}/archive")
async def archive_topic(topic_id: str, user_id: str = Depends(require_auth)):
    """Archive a topic. Only active topics can be archived."""
    await _topic_service.archive_topic(topic_id, user_id)
    return {"status": "archived", "topicId": topic_id}


@router.post("/topic/{topic_id}/message")
async def send_message(
    topic_id: str, body: SendMessageRequest, user_id: str = Depends(require_auth)
):
    """Send a message within a topic.

    Triggers the full chat flow: appends user message, assembles context,
    calls LLM, appends assistant response, and checks for compaction.
    """
    result = await _chat_service.handle_message(topic_id, user_id, body.content, body.mode)
    return result
