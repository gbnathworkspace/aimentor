"""Topics router — /api/topics and /api/topic/:id CRUD + messaging endpoints.

Provides topic creation, listing, retrieval, renaming, archival, and
per-topic message sending. All routes enforce authenticated userId ownership
and return identical 404 responses for not-found and unauthorized to prevent
topic ID enumeration (Req 15.5).

Requirements: 1.1, 1.2, 1.3, 2.4, 3.1, 3.3, 4.1, 14.4, 15.1, 15.2, 15.3, 15.5
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.auth.dependencies import require_auth
from app.config.database import weight_nudges_col, skill_graph_col
from app.services.topic_service import TopicService
from app.services.topic_chat_service import TopicChatService
from app.services.topic_router import route_topic
from app.services.subtopic_weights import derive_subtopic_weights, get_subtopics

router = APIRouter(prefix="/api", tags=["Topics"])

_topic_service = TopicService()
_chat_service = TopicChatService()


# --- Request/Response Models ---


class CreateTopicRequest(BaseModel):
    """Request body for creating a new topic."""

    title: str = Field(..., min_length=1, max_length=100)


class UpdateTopicRequest(BaseModel):
    """Request body for updating a topic (rename and/or set subject)."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    # Empty string clears the subject (moves the topic back to Ungrouped).
    subject: Optional[str] = Field(default=None, max_length=60)


class RouteTopicRequest(BaseModel):
    """Request body for routing a welcome-screen message to an existing topic."""

    text: str = Field(..., min_length=1, max_length=2000)


class SendMessageRequest(BaseModel):
    """Request body for sending a message within a topic."""

    content: str = Field(..., min_length=1, max_length=50000)
    mode: str = Field(default="topic")


class ResolveL1ScopeRequest(BaseModel):
    """Request body for manually resolving an l1_scope entry (see
    .kiro/specs/topic-scoping) — normally one the classifier judged
    "uncertain"."""

    situation: str = Field(..., min_length=1, max_length=500)
    relevant: bool


class SubtopicWeightsRequest(BaseModel):
    """Request body for DeriveSubtopicWeights (see .kiro/specs/skill-graph-v2)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    goal: Literal["job_performance"]
    work_evidence: Optional[str] = Field(default=None, max_length=20000)
    # A stated goal ("preparing for a job interview") rather than a body of
    # evidence — scored by relevance instead of mention-counting.
    goal_intent: Optional[str] = Field(default=None, max_length=500)
    pairwise_comparisons: Optional[list[tuple[str, str]]] = None
    user_nudges: Optional[dict[str, float]] = None


class WeightFlagResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    subtopic: str
    baseline: float
    final: float
    delta: float


class SubtopicWeightsResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    subtopics: list[str]
    weights: Optional[dict[str, float]]
    flags: list[WeightFlagResponse]
    needs_pairwise: bool
    # 0-100 estimated mastery per subtopic — only set on the goal_intent path
    # (see derive_subtopic_weights); None elsewhere.
    proficiency: Optional[dict[str, float]] = None


class NudgeFlagLogRequest(BaseModel):
    """Body for logging large user/computed-weight disagreements (spec step 6)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    flags: list[WeightFlagResponse]


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


@router.post("/topics/route")
async def route_topic_endpoint(body: RouteTopicRequest, user_id: str = Depends(require_auth)):
    """Suggest which existing topic (if any) a welcome-screen message
    continues — a semantic judgment call replacing the old client-side
    keyword-overlap heuristic. Still just a suggestion: the frontend shows
    it as a confirm/override dialog (a single match) or a short pick-list
    (an ambiguous call, up to 4 candidates), never a silent reroute.
    """
    topics = await _topic_service.list_topics(user_id)
    titles_by_id = {t["topicId"]: t["title"] for t in topics}
    result = await route_topic(body.text, topics)

    if result.topic_id:
        return {"topicId": result.topic_id, "title": titles_by_id.get(result.topic_id), "candidates": []}

    candidates = [
        {"topicId": tid, "title": titles_by_id[tid]} for tid in result.related_ids if tid in titles_by_id
    ]
    return {"topicId": None, "title": None, "candidates": candidates}


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
async def update_topic(
    topic_id: str, body: UpdateTopicRequest, user_id: str = Depends(require_auth)
):
    """Update a topic's title and/or subject.

    Title is validated (1-100 chars after trim) when present. An empty
    subject string clears the subject (Ungrouped).
    """
    topic = await _topic_service.update_topic(
        topic_id, user_id, title=body.title, subject=body.subject
    )
    return topic


@router.post("/topic/{topic_id}/archive")
async def archive_topic(topic_id: str, user_id: str = Depends(require_auth)):
    """Archive a topic. Only active topics can be archived."""
    await _topic_service.archive_topic(topic_id, user_id)
    return {"status": "archived", "topicId": topic_id}


@router.delete("/topic/{topic_id}")
async def delete_topic(topic_id: str, user_id: str = Depends(require_auth)):
    """Permanently delete a topic and its cascade collections.

    Accepts topics in both active and archived status — unlike archive_topic,
    which rejects non-active topics with 409. Returns 404 for both not-found
    and non-owner cases to prevent topic ID enumeration (Req 15.5).

    Requirements: 3.1, 3.3, 3.4, 3.5
    """
    await _topic_service.delete_topic(topic_id, user_id)
    return {"ok": True}


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


@router.post("/topic/{topic_id}/l1-scope/resolve")
async def resolve_l1_scope(
    topic_id: str, body: ResolveL1ScopeRequest, user_id: str = Depends(require_auth)
):
    """Manually resolve one l1_scope entry — normally one classify_relevance
    judged "uncertain". The answer is marked userResolved and survives a
    later profile-triggered recompute (see TopicService._merge_l1_scope).

    See .kiro/specs/topic-scoping.
    """
    await _topic_service.resolve_l1_scope_item(
        topic_id, user_id, body.situation, body.relevant
    )
    return {"ok": True}


@router.post("/topic/{topic_id}/subtopic-weights", response_model=SubtopicWeightsResponse)
async def get_subtopic_weights(
    topic_id: str, body: SubtopicWeightsRequest, user_id: str = Depends(require_auth)
):
    """Weight this topic's subtopics (DeriveSubtopicWeights).

    Caller supplies either work_evidence (commits, tickets, PR comments —
    counted by mention, since that evidence isn't web-searchable) or
    goal_intent (a stated goal — scored by relevance instead).
    """
    topic = await _topic_service.get_topic(topic_id, user_id)
    subtopics = await get_subtopics(topic["title"])

    # L2 skill graph node for this topic (if any) anchors the proficiency
    # estimate — a "beginner" overall level keeps per-subtopic mastery
    # scores from drifting high just because the stated intent sounds
    # confident. Default matches SkillNode's own onboarding default.
    skill_node = await skill_graph_col().find_one(
        {"user_id": user_id, "topic": topic["title"]},
        {"current_level": 1, "_id": 0},
    )
    current_level = (skill_node or {}).get("current_level", "beginner")

    try:
        result = await derive_subtopic_weights(
            topic=topic["title"],
            goal=body.goal,
            subtopics=subtopics,
            work_evidence=body.work_evidence,
            goal_intent=body.goal_intent,
            pairwise_comparisons=body.pairwise_comparisons,
            user_nudges=body.user_nudges,
            current_level=current_level,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SubtopicWeightsResponse(
        subtopics=result.subtopics,
        weights=result.weights,
        flags=[
            WeightFlagResponse(subtopic=f.subtopic, baseline=f.baseline, final=f.final, delta=f.delta)
            for f in result.flags
        ],
        needs_pairwise=result.needs_pairwise,
        proficiency=result.proficiency,
    )


@router.post("/topic/{topic_id}/subtopic-weights/nudge-log")
async def log_nudge_flags(
    topic_id: str, body: NudgeFlagLogRequest, user_id: str = Depends(require_auth)
):
    """Persist large user/computed-weight disagreements (spec step 6).

    The nudge UI recomputes weights client-side for instant feedback, so
    without this call a flagged disagreement vanished the moment the modal
    closed — this is the only place that signal gets kept.
    """
    if not body.flags:
        return {"logged": 0}

    topic = await _topic_service.get_topic(topic_id, user_id)
    now = datetime.now(timezone.utc).isoformat()
    await weight_nudges_col().insert_many([
        {
            "user_id": user_id,
            "topic_id": topic_id,
            "topic": topic["title"],
            "subtopic": f.subtopic,
            "baseline": f.baseline,
            "final": f.final,
            "delta": f.delta,
            "created_at": now,
        }
        for f in body.flags
    ])
    return {"logged": len(body.flags)}
