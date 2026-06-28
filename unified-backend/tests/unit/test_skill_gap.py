"""Issue #3: session skill levels must align with compute_gap's vocabulary.

The bug was a vocab split — session emitted novice/medium+/hard while the graph
(and compute_gap) spoke beginner/intermediate/advanced/expert, so every gap
silently defaulted. These assert the normalized vocab feeds compute_gap directly.
"""

from app.models.session import SkillLevel
from app.services.onboarding_bootstrap import compute_gap


def test_every_session_level_is_understood_by_compute_gap():
    # If a SkillLevel value were unknown to compute_gap it would default to
    # "beginner" — so a current==required check returning "none" proves alignment.
    for level in SkillLevel:
        assert compute_gap(level.value, level.value) == "none", level.value


def test_gap_scales_with_distance():
    assert compute_gap("expert", SkillLevel.beginner.value) == "large"
    assert compute_gap("advanced", SkillLevel.intermediate.value) == "small"
    assert compute_gap("intermediate", SkillLevel.expert.value) == "none"  # over-qualified
