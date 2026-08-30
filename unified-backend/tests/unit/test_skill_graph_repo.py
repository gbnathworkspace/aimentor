"""apply_update merges only the touched subtopics into subtopic_mastery
(see .kiro/specs/skill-graph-subtopic-mastery) — never a whole-map replace."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.models.skill import SubtopicMasteryUpdate
import app.services.skill_graph_repo as repo


def _run_apply(subtopic_updates):
    """Run apply_update against a mocked collection; return the captured $set."""
    captured = {}
    fake = AsyncMock()

    async def cap(_filter, update, **_kw):
        captured.update(update["$set"])

    fake.update_one = AsyncMock(side_effect=cap)

    async def go():
        with patch.object(repo, "skill_graph_col", return_value=fake):
            await repo.apply_update("u1", "Graphs", subtopic_updates)

    asyncio.run(go())
    return captured


def test_writes_dotted_path_per_subtopic():
    written = _run_apply([SubtopicMasteryUpdate(subtopic="BFS", mastery=80)])
    assert written["subtopic_mastery.BFS"] == 80


def test_touches_only_the_given_subtopics():
    """Two updates in one call only ever set those two keys — apply_update
    never reads or overwrites the rest of the map (Mongo's dotted-path $set
    does the merge, not a find-then-replace)."""
    written = _run_apply([
        SubtopicMasteryUpdate(subtopic="BFS", mastery=80),
        SubtopicMasteryUpdate(subtopic="DFS", mastery=40),
    ])
    assert written["subtopic_mastery.BFS"] == 80
    assert written["subtopic_mastery.DFS"] == 40
    assert not any(k.startswith("subtopic_mastery.") and k not in
                   {"subtopic_mastery.BFS", "subtopic_mastery.DFS"} for k in written)




def test_empty_updates_is_a_noop():
    """No subtopics with signal → no write at all, not an empty $set."""
    captured = {}
    fake = AsyncMock()
    fake.update_one = AsyncMock(side_effect=lambda *a, **k: captured.setdefault("called", True))

    async def go():
        with patch.object(repo, "skill_graph_col", return_value=fake):
            await repo.apply_update("u1", "Graphs", [])

    asyncio.run(go())
    assert "called" not in captured
