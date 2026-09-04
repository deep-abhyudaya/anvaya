"""Dataset version metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class DatasetVersion(SQLModel, table=True):
    __tablename__ = "dataset_versions"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: str = Field(unique=True, index=True, max_length=64)
    generator_version: str = Field(max_length=32)
    seed: int = 0
    config_hash: str = Field(max_length=64)

    train_count: int = 0
    validation_count: int = 0
    test_count: int = 0
    replay_count: int = 0

    normal_count: int = 0
    attack_count: int = 0
    suspicious_count: int = 0

    scenario_count: int = 0
    scenarios_json: str = ""

    schema_valid: bool = False
    leakage_check_passed: bool = False
    validation_report_json: str = ""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
