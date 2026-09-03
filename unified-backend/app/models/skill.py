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
    # flag. The cold-start gate (mode_router.py Rule 1) reads the sibling
    # `last_studied` field instead of this one, since last_studied is set
    # by any skill_graph write, not just a diagnostic verdict.
    subtopic_mastery: dict[str, float] = Field(default_factory=dict)
    # ISO timestamp of the last mastery update per subtopic — set alongside
    # subtopic_mastery in skill_graph_repo.apply_update, never independently.
    subtopic_last_studied: dict[str, str] = Field(default_factory=dict)


class SkillUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    # Merged into the existing map (touched keys only), not a replacement —
    # see skill_graph_repo.apply_update.
    subtopic_mastery: Optional[dict[str, float]] = None
