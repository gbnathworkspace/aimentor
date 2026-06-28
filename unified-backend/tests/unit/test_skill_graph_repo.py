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
                SessionSkillUpdate(topic="Graphs", new_level=SkillLevel.advanced, gap=20),
            )

    asyncio.run(go())
    return captured


def test_previous_level_captured_from_existing():
    written = _run_apply({"required_level": "expert", "current_level": "intermediate"})
    assert written["previous_level"] == "intermediate"
    assert written["current_level"] == "advanced"


def test_previous_level_none_for_new_topic():
    written = _run_apply(None)  # no existing node
    assert written["previous_level"] is None
    assert written["current_level"] == "advanced"
