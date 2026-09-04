"""Telemetry event model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

from anvaya.models.enums import TelemetryEventType


class TelemetryEvent(SQLModel, table=True):
    __tablename__ = "telemetry_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: Optional[str] = Field(default=None, index=True, max_length=64)
    scenario_id: str = Field(default="", index=True, max_length=128)

    event_type: TelemetryEventType = Field(index=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    actor: str = Field(default="", max_length=128)
    host: str = Field(default="", max_length=128)
    process: str = Field(default="", max_length=256)
    source: str = Field(default="", max_length=128)
    destination: str = Field(default="", max_length=128)
    command: str = ""

    is_off_hours: bool = False
    is_new_device: bool = False
    is_privilege_escalation: bool = False
    is_anomalous_process: bool = False
    is_unusual_network: bool = False
    is_lateral_movement: bool = False

    is_attack: bool = False
    attack_family: str = Field(default="", max_length=128)
    ground_truth_label: str = Field(default="normal", max_length=32)

    replay_id: str = Field(default="", max_length=128)
    is_replay: bool = False

    raw_data: str = ""

    seed: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
