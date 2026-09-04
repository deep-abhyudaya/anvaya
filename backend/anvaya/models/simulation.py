"""Simulation models for Threat Ecosystem and BlastScope."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Simulation(SQLModel, table=True):
    __tablename__ = "simulations"

    id: Optional[int] = Field(default=None, primary_key=True)
    simulation_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)
    simulation_type: str = Field(max_length=64)
    mode: str = Field(default="contain", max_length=32)
    status: str = Field(default="pending", max_length=32)
    ecosystem_health: float = 0.0
    total_steps: int = 0
    current_step: int = 0
    result_json: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class SimulationStep(SQLModel, table=True):
    __tablename__ = "simulation_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    simulation_id: str = Field(index=True, max_length=64)
    step_number: int = 0
    step_type: str = Field(max_length=64)
    description: str = ""
    nodes_affected_json: str = ""
    edges_affected_json: str = ""
    result: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
