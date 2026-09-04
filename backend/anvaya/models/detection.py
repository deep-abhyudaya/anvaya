"""Detection run and result models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class DetectionRun(SQLModel, table=True):
    __tablename__ = "detection_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)
    scenario_id: str = Field(default="", index=True, max_length=128)

    model_version_id: Optional[int] = Field(default=None, foreign_key="model_versions.id")
    rule_id: Optional[int] = Field(default=None, foreign_key="detection_rules.id")

    detected: bool = False
    score: float = 0.0
    threshold: float = 0.0
    is_replay: bool = False
    replay_id: str = Field(default="", max_length=128)

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    inference_latency_ms: float = 0.0

    events_processed: int = 0
    events_flagged: int = 0


class DetectionResult(SQLModel, table=True):
    __tablename__ = "detection_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, max_length=64)
    event_id: str = Field(index=True, max_length=64)
    detected: bool = False
    score: float = 0.0
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
