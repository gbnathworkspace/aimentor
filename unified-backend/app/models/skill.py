"""L2 Skill Graph Pydantic models."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SubtopicMasteryUpdate(BaseModel):
    """One (subtopic, mastery) pair extracted from a diagnostic verdict or
    compaction skill extraction. Validated against a topic's canonical
    subtopic list before being merged into SkillNode.subtopic_mastery —
    see skill_graph_repo.apply_update."""

    subtopic: str
    mastery: float = Field(ge=0, le=100)


class SkillNode(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    topic: str
    # Per-subtopic mastery, 0-100, keyed by the topic's cached subtopic list
    # (see subtopic_weights.get_subtopics). Updated incrementally — a merge
    # only ever overwrites the subtopics it has evidence for (see
    # skill_graph_repo.apply_update). Replaces the old single current_level
    # enum, which couldn't represent uneven mastery within one topic.
    #
    # An empty dict IS "not assessed yet" — there's no separate `assessed`
    # flag, since that would just be a second field mirroring this one
    # (issue #50's cold-start gate reads `not subtopic_mastery` directly).
    subtopic_mastery: dict[str, float] = Field(default_factory=dict)


class SkillUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    # Merged into the existing map (touched keys only), not a replacement —
    # see skill_graph_repo.apply_update.
    subtopic_mastery: Optional[dict[str, float]] = None
