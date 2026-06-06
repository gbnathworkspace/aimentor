"""Unit tests for app/models/validators.py."""

import pytest

from app.models.schemas import ChunkMetadata, CoreProfileIngestion, SkillGraphSignals
from app.models.validators import (
    ValidationError,
    validate_core_profile,
    validate_session_embedding_metadata,
    validate_skill_graph_signals,
)


class TestValidationError:
    """Tests for the custom ValidationError class."""

    def test_stores_fields(self):
        err = ValidationError(fields=["field_a", "field_b"], message="test error")
        assert err.fields == ["field_a", "field_b"]
        assert err.message == "test error"

    def test_default_message(self):
        err = ValidationError(fields=["x"])
        assert err.message == "Validation failed"

    def test_str_contains_fields(self):
        err = ValidationError(fields=["a", "b"], message="bad")
        assert "a" in str(err)
        assert "b" in str(err)


class TestValidateCoreProfile:
    """Tests for validate_core_profile."""

    def test_valid_full_profile(self):
        data = {
            "current_role": "Software Engineer",
            "years_of_experience": 5,
            "education": "BS Computer Science",
            "skills": ["Python", "FastAPI", "MongoDB"],
        }
        result = validate_core_profile(data)
        assert isinstance(result, CoreProfileIngestion)
        assert result.current_role == "Software Engineer"
        assert result.years_of_experience == 5
        assert result.skills == ["Python", "FastAPI", "MongoDB"]

    def test_valid_empty_profile(self):
        result = validate_core_profile({})
        assert isinstance(result, CoreProfileIngestion)
        assert result.current_role is None
        assert result.years_of_experience is None
        assert result.skills == []

    def test_valid_with_none_fields(self):
        data = {
            "current_role": None,
            "years_of_experience": None,
            "education": None,
            "skills": [],
        }
        result = validate_core_profile(data)
        assert result.current_role is None

    def test_invalid_skills_not_list(self):
        data = {"skills": "not a list"}
        with pytest.raises(ValidationError) as exc_info:
            validate_core_profile(data)
        assert "skills" in exc_info.value.fields

    def test_invalid_skills_not_strings(self):
        data = {"skills": [1, 2, 3]}
        with pytest.raises(ValidationError) as exc_info:
            validate_core_profile(data)
        assert "skills" in exc_info.value.fields

    def test_invalid_years_negative(self):
        data = {"years_of_experience": -1}
        with pytest.raises(ValidationError) as exc_info:
            validate_core_profile(data)
        assert "years_of_experience" in exc_info.value.fields

    def test_invalid_years_not_int(self):
        data = {"years_of_experience": "five"}
        with pytest.raises(ValidationError) as exc_info:
            validate_core_profile(data)
        assert "years_of_experience" in exc_info.value.fields

    def test_invalid_years_float(self):
        data = {"years_of_experience": 3.5}
        with pytest.raises(ValidationError) as exc_info:
            validate_core_profile(data)
        assert "years_of_experience" in exc_info.value.fields

    def test_multiple_failing_fields(self):
        data = {"skills": 123, "years_of_experience": -2}
        with pytest.raises(ValidationError) as exc_info:
            validate_core_profile(data)
        assert "skills" in exc_info.value.fields
        assert "years_of_experience" in exc_info.value.fields


class TestValidateSkillGraphSignals:
    """Tests for validate_skill_graph_signals."""

    def test_valid_full_signals(self):
        data = {
            "leetcode_solved": {"easy": 10, "medium": 5, "hard": 2},
            "mentor_eval_score": "B+",
            "mentor_eval_count": 3,
        }
        result = validate_skill_graph_signals(data)
        assert isinstance(result, SkillGraphSignals)
        assert result.leetcode_solved.easy == 10
        assert result.mentor_eval_count == 3

    def test_valid_empty_signals(self):
        result = validate_skill_graph_signals({})
        assert isinstance(result, SkillGraphSignals)
        assert result.leetcode_solved is None
        assert result.mentor_eval_count == 0

    def test_valid_with_none_leetcode(self):
        data = {"leetcode_solved": None}
        result = validate_skill_graph_signals(data)
        assert result.leetcode_solved is None

    def test_invalid_leetcode_negative_easy(self):
        data = {"leetcode_solved": {"easy": -1, "medium": 0, "hard": 0}}
        with pytest.raises(ValidationError) as exc_info:
            validate_skill_graph_signals(data)
        assert "leetcode_solved.easy" in exc_info.value.fields

    def test_invalid_leetcode_negative_medium(self):
        data = {"leetcode_solved": {"easy": 0, "medium": -5, "hard": 0}}
        with pytest.raises(ValidationError) as exc_info:
            validate_skill_graph_signals(data)
        assert "leetcode_solved.medium" in exc_info.value.fields

    def test_invalid_leetcode_negative_hard(self):
        data = {"leetcode_solved": {"easy": 0, "medium": 0, "hard": -3}}
        with pytest.raises(ValidationError) as exc_info:
            validate_skill_graph_signals(data)
        assert "leetcode_solved.hard" in exc_info.value.fields

    def test_invalid_mentor_eval_count_negative(self):
        data = {"mentor_eval_count": -1}
        with pytest.raises(ValidationError) as exc_info:
            validate_skill_graph_signals(data)
        assert "mentor_eval_count" in exc_info.value.fields

    def test_invalid_mentor_eval_count_not_int(self):
        data = {"mentor_eval_count": "many"}
        with pytest.raises(ValidationError) as exc_info:
            validate_skill_graph_signals(data)
        assert "mentor_eval_count" in exc_info.value.fields


class TestValidateSessionEmbeddingMetadata:
    """Tests for validate_session_embedding_metadata."""

    def test_valid_session_metadata(self):
        data = {
            "user_id": "user_123",
            "source": "session_summary",
            "chunk_index": 0,
            "session_id": "sess_abc",
            "date": "2024-01-15",
            "type": "mock_interview",
            "topic": "Dynamic Programming",
            "topic_category": "DSA",
        }
        result = validate_session_embedding_metadata(data)
        assert isinstance(result, ChunkMetadata)
        assert result.user_id == "user_123"
        assert result.session_id == "sess_abc"

    def test_missing_user_id(self):
        data = {
            "source": "session_summary",
            "chunk_index": 0,
            "session_id": "sess_abc",
            "date": "2024-01-15",
            "type": "mock_interview",
            "topic": "DP",
            "topic_category": "DSA",
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_session_embedding_metadata(data)
        assert "user_id" in exc_info.value.fields

    def test_missing_source(self):
        data = {
            "user_id": "user_123",
            "chunk_index": 0,
            "session_id": "sess_abc",
            "date": "2024-01-15",
            "type": "mock_interview",
            "topic": "DP",
            "topic_category": "DSA",
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_session_embedding_metadata(data)
        assert "source" in exc_info.value.fields

    def test_missing_chunk_index(self):
        data = {
            "user_id": "user_123",
            "source": "session_summary",
            "session_id": "sess_abc",
            "date": "2024-01-15",
            "type": "mock_interview",
            "topic": "DP",
            "topic_category": "DSA",
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_session_embedding_metadata(data)
        assert "chunk_index" in exc_info.value.fields

    def test_missing_session_id(self):
        data = {
            "user_id": "user_123",
            "source": "session_summary",
            "chunk_index": 0,
            "date": "2024-01-15",
            "type": "mock_interview",
            "topic": "DP",
            "topic_category": "DSA",
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_session_embedding_metadata(data)
        assert "session_id" in exc_info.value.fields

    def test_missing_multiple_session_fields(self):
        data = {
            "user_id": "user_123",
            "source": "session_summary",
            "chunk_index": 0,
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_session_embedding_metadata(data)
        assert "session_id" in exc_info.value.fields
        assert "date" in exc_info.value.fields
        assert "type" in exc_info.value.fields
        assert "topic" in exc_info.value.fields
        assert "topic_category" in exc_info.value.fields

    def test_null_required_field_rejected(self):
        data = {
            "user_id": None,
            "source": "session_summary",
            "chunk_index": 0,
            "session_id": "sess_abc",
            "date": "2024-01-15",
            "type": "mock_interview",
            "topic": "DP",
            "topic_category": "DSA",
        }
        with pytest.raises(ValidationError) as exc_info:
            validate_session_embedding_metadata(data)
        assert "user_id" in exc_info.value.fields
