"""Issue #16: apply_update records previous_level for the 'since last session' delta."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.models.session import SessionSkillUpdate, SkillLevel
import app.services.skill_graph_repo as repo


def _run_apply(existing):
    """Run apply_update against a mocked collection; return the captured $set."""
    captured = {}
    fake = AsyncMock()
    fake.find_one = AsyncMock(return_value=existing)

    async def cap(_filter, update, **_kw):
        captured.update(update["$set"])

    fake.update_one = AsyncMock(side_effect=cap)

    async def go():
        with patch.object(repo, "skill_graph_col", return_value=fake):
            await repo.apply_update(
                "u1",
                SessionSkillUpdate(topic="Graphs", new_level=SkillLevel.advanced),
            )

    asyncio.run(go())
    return captured


def test_previous_level_captured_from_existing():
    written = _run_apply({"current_level": "intermediate"})
    assert written["previous_level"] == "intermediate"
    assert written["current_level"] == "advanced"


def test_previous_level_none_for_new_topic():
    written = _run_apply(None)  # no existing node
    assert written["previous_level"] is None
    assert written["current_level"] == "advanced"


def test_apply_update_marks_assessed_true():
    """Issue #50: any verified write flips assessed, distinguishing it from
    the onboarding placeholder guess."""
    written = _run_apply({"current_level": "beginner", "assessed": False})
    assert written["assessed"] is True


class TestNextBestTopics:
    """Issue #10: prerequisite-ordered next-best-skill sequencing."""

    def test_orders_prerequisites_before_dependents(self):
        nodes = [
            {"topic": "Algorithms", "current_level": "beginner", "prerequisites": ["Data Structures"]},
            {"topic": "Data Structures", "current_level": "beginner", "prerequisites": []},
        ]
        ranked = repo.next_best_topics(nodes)
        assert [n["topic"] for n in ranked] == ["Data Structures", "Algorithms"]

    def test_respects_limit(self):
        nodes = [{"topic": f"T{i}", "current_level": "beginner", "prerequisites": []} for i in range(5)]
        assert len(repo.next_best_topics(nodes, limit=2)) == 2

    def test_missing_prerequisite_is_ignored(self):
        nodes = [{"topic": "Solo", "current_level": "beginner", "prerequisites": ["Nonexistent"]}]
        ranked = repo.next_best_topics(nodes)
        assert [n["topic"] for n in ranked] == ["Solo"]
