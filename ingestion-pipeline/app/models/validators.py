"""Zod-style validation functions for ingestion pipeline writes.

Provides validators for Core Profile writes, Skill Graph writes, and session
embedding metadata. Each validator uses Pydantic's model_validate under the hood
and raises a custom ValidationError with specific failing field names.
"""

from pydantic import ValidationError as PydanticValidationError

from app.models.schemas import ChunkMetadata, CoreProfileIngestion, SkillGraphSignals


class ValidationError(Exception):
    """Custom validation error that includes the list of failing field names.

    Attributes:
        fields: List of field names that failed validation.
        message: Human-readable error description.
    """

    def __init__(self, fields: list[str], message: str = "Validation failed"):
        self.fields = fields
        self.message = message
        super().__init__(f"{message}: {', '.join(fields)}")


def _extract_field_names(exc: PydanticValidationError) -> list[str]:
    """Extract unique field names from a Pydantic ValidationError."""
    fields: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        if loc:
            # Use the first element of the location tuple as the field name
            fields.append(str(loc[0]))
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_fields: list[str] = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            unique_fields.append(f)
    return unique_fields


def validate_core_profile(data: dict) -> CoreProfileIngestion:
    """Validate data matches CoreProfileIngestion schema.

    Performs additional semantic validations beyond Pydantic schema:
    - If `skills` is present, it must be a list of strings.
    - If `years_of_experience` is present, it must be a non-negative int.

    Args:
        data: Dictionary of core profile fields to validate.

    Returns:
        A validated CoreProfileIngestion instance.

    Raises:
        ValidationError: If any field fails validation, includes failing field names.
    """
    failing_fields: list[str] = []

    # Pre-validate semantic constraints before Pydantic model validation
    if "skills" in data and data["skills"] is not None:
        if not isinstance(data["skills"], list):
            failing_fields.append("skills")
        elif not all(isinstance(s, str) for s in data["skills"]):
            failing_fields.append("skills")

    if "years_of_experience" in data and data["years_of_experience"] is not None:
        if not isinstance(data["years_of_experience"], int):
            failing_fields.append("years_of_experience")
        elif data["years_of_experience"] < 0:
            failing_fields.append("years_of_experience")

    if failing_fields:
        raise ValidationError(
            fields=failing_fields,
            message="Core profile validation failed",
        )

    try:
        return CoreProfileIngestion.model_validate(data)
    except PydanticValidationError as exc:
        fields = _extract_field_names(exc)
        raise ValidationError(
            fields=fields,
            message="Core profile validation failed",
        ) from exc


def validate_skill_graph_signals(data: dict) -> SkillGraphSignals:
    """Validate data matches SkillGraphSignals schema.

    Performs additional semantic validations:
    - `leetcode_solved` fields (easy/medium/hard) must be non-negative ints.
    - `mentor_eval_count` must be non-negative.

    Args:
        data: Dictionary of skill graph signal fields to validate.

    Returns:
        A validated SkillGraphSignals instance.

    Raises:
        ValidationError: If any field fails validation, includes failing field names.
    """
    failing_fields: list[str] = []

    # Pre-validate leetcode_solved sub-fields
    if "leetcode_solved" in data and data["leetcode_solved"] is not None:
        leetcode = data["leetcode_solved"]
        if isinstance(leetcode, dict):
            for field_name in ("easy", "medium", "hard"):
                if field_name in leetcode:
                    value = leetcode[field_name]
                    if not isinstance(value, int) or value < 0:
                        failing_fields.append(f"leetcode_solved.{field_name}")

    # Pre-validate mentor_eval_count
    if "mentor_eval_count" in data:
        value = data["mentor_eval_count"]
        if not isinstance(value, int) or value < 0:
            failing_fields.append("mentor_eval_count")

    if failing_fields:
        raise ValidationError(
            fields=failing_fields,
            message="Skill graph signals validation failed",
        )

    try:
        return SkillGraphSignals.model_validate(data)
    except PydanticValidationError as exc:
        fields = _extract_field_names(exc)
        raise ValidationError(
            fields=fields,
            message="Skill graph signals validation failed",
        ) from exc


def validate_session_embedding_metadata(data: dict) -> ChunkMetadata:
    """Validate session embedding metadata has required non-null fields.

    For session embeddings, the following fields are required and must be non-null:
    - user_id, source, chunk_index (always required)
    - session_id, date, type, topic, topic_category (required for session embeddings)

    Args:
        data: Dictionary of chunk metadata fields to validate.

    Returns:
        A validated ChunkMetadata instance.

    Raises:
        ValidationError: If any required field is missing or null.
    """
    failing_fields: list[str] = []

    # Base required fields (must be present and non-null)
    base_required = ["user_id", "source", "chunk_index"]
    for field_name in base_required:
        if field_name not in data or data[field_name] is None:
            failing_fields.append(field_name)

    # Session-specific required fields (must be non-null for session embeddings)
    session_required = ["session_id", "date", "type", "topic", "topic_category"]
    for field_name in session_required:
        if field_name not in data or data[field_name] is None:
            failing_fields.append(field_name)

    if failing_fields:
        raise ValidationError(
            fields=failing_fields,
            message="Session embedding metadata validation failed",
        )

    try:
        return ChunkMetadata.model_validate(data)
    except PydanticValidationError as exc:
        fields = _extract_field_names(exc)
        raise ValidationError(
            fields=fields,
            message="Session embedding metadata validation failed",
        ) from exc
