"""Subagent execution model for Devin-like child agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class SubagentExecution(SQLModel, table=True):
    """A child execution spawned by a parent agent execution."""

    __tablename__ = "subagent_executions"

    id: Optional[int] = Field(default=None, primary_key=True)
    subagent_id: str = Field(unique=True, index=True, max_length=64)
    parent_execution_id: str = Field(index=True, max_length=64)
    child_execution_id: Optional[str] = Field(default=None, index=True, max_length=64)
    profile_id: str = Field(max_length=64)
    title: str = ""
    task: str = ""
    mode: str = "background"
    status: str = "pending"
    started_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    result_summary: str = ""
    error_message: str = ""
    tool_calls_count: int = 0
    nesting_depth: int = 0
