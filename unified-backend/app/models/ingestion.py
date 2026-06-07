"""Ingestion job Pydantic models."""

from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    job_id: str
    status: str
    message: str
    completed_at: Optional[str] = None
