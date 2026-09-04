"""Execution and execution-event models for the agentic layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Execution(SQLModel, table=True):
    """A single agent execution started from a user objective."""

    __tablename__ = "executions"

    id: Optional[int] = Field(default=None, primary_key=True)
    execution_id: str = Field(unique=True, index=True, max_length=64)
    objective: str = ""
    incident_id: str = Field(default="", index=True, max_length=64)

    status: str = Field(default="pending", index=True, max_length=32)

    provider: str = Field(default="anvaya", max_length=64)
    mode: str = Field(default="", max_length=32)
    fallback_used: bool = False
    fallback_reason: str = ""

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0

    result_summary: str = ""
    error_code: str = ""
    error_message: str = ""


class ExecutionEvent(SQLModel, table=True):
    """Observable event in an agent execution trace."""

    __tablename__ = "execution_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    execution_id: str = Field(index=True, max_length=64)
    sequence: int = Field(index=True)

    type: str = Field(max_length=64)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    tool_call_id: str = Field(default="", max_length=64)
    tool_name: str = Field(default="", max_length=128)
    provider: str = Field(default="", max_length=64)
    status: str = Field(default="", max_length=32)

    label: str = ""
    payload_json: str = ""

    artifact_ref: str = ""
    artifact_type: str = ""

    error_code: str = ""
    error_message: str = ""
    fallback_reason: str = ""

    class Config:  # type: ignore[override]
        pass
