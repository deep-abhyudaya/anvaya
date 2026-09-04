"""Replay run model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

from anvaya.models.enums import ReplayStatus


class ReplayRun(SQLModel, table=True):
    __tablename__ = "replay_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    replay_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)
    scenario_id: str = Field(default="", index=True, max_length=128)
    scenario_seed: int = 0

    pre_patch_rule_id: Optional[str] = Field(default=None, max_length=64)
    pre_patch_detected: bool = False
    pre_patch_score: float = 0.0

    post_patch_rule_id: Optional[str] = Field(default=None, max_length=64)
    post_patch_detected: bool = False
    post_patch_score: float = 0.0

    status: ReplayStatus = Field(default=ReplayStatus.PENDING, index=True)
    is_identical: bool = True

    timeline_json: str = ""

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    repair_iterations: int = 0
    max_iterations: int = 3
