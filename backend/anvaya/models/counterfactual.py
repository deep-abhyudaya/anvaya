"""Counterfactual analysis model for What-If engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class CounterfactualAnalysis(SQLModel, table=True):
    __tablename__ = "counterfactual_analyses"

    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)
    model_version: str = ""

    original_score: float = 0.0
    original_features_json: str = ""

    counterfactual_score: float = 0.0
    changed_features_json: str = ""
    score_delta: float = 0.0
    explanation: str = ""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
