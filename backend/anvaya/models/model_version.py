"""Model version tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class ModelVersion(SQLModel, table=True):
    __tablename__ = "model_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    model_id: str = Field(unique=True, index=True, max_length=64)
    model_type: str = Field(max_length=64)
    version: str = Field(max_length=32)
    status: str = Field(default="active", max_length=32)

    dataset_version: str = ""
    feature_schema_json: str = ""
    training_samples: int = 0
    validation_samples: int = 0

    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    inference_latency_ms: float = 0.0

    artifact_path: str = ""
    artifact_hash: str = ""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: Optional[datetime] = None
