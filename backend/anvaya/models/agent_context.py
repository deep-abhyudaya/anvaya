"""Live execution context for the reasoning-aware agent loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ExecutionContext(SQLModel, table=True):
    """Mutable, user-visible context for an in-flight agent execution.

    This is stored in a separate table so the existing ``Execution`` and
    ``ExecutionEvent`` schemas are not modified. The context is updated at
    every step and is the source of truth for the live plan, observations,
    user follow-up messages, and current action.
    """

    __tablename__ = "execution_contexts"

    id: Optional[int] = Field(default=None, primary_key=True)
    execution_id: str = Field(unique=True, index=True, max_length=64)

    objective: str = ""
    incident_id: str = Field(default="", index=True, max_length=64)
    project_id: str = Field(default="", max_length=64)

    plan: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    observations: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    messages: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    mission_json: str = Field(default="", sa_column=Column(Text))
    blackboard_json: str = Field(default="", sa_column=Column(Text))
    hypotheses_json: str = Field(default="", sa_column=Column(Text))
    memory_json: str = Field(default="", sa_column=Column(Text))
    findings_json: str = Field(default="", sa_column=Column(Text))
    verification_json: str = Field(default="", sa_column=Column(Text))

    reasoning_summary: str = ""
    current_action: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    model: str = Field(default="", max_length=128)
    provider: str = Field(default="", max_length=64)
    status: str = Field(default="running", max_length=32)

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def _load(self, raw: str) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _dump(self, value: Any) -> str:
        return json.dumps(value, default=str) if value else ""

    def get_mission(self) -> Any:
        return self._load(self.mission_json)

    def set_mission(self, value: Any) -> None:
        self.mission_json = self._dump(value)

    def get_blackboard(self) -> Any:
        return self._load(self.blackboard_json)

    def set_blackboard(self, value: Any) -> None:
        self.blackboard_json = self._dump(value)

    def get_hypotheses(self) -> list[Any]:
        data = self._load(self.hypotheses_json)
        return data if isinstance(data, list) else []

    def set_hypotheses(self, value: list[Any]) -> None:
        self.hypotheses_json = self._dump(value)

    def get_memory(self) -> Any:
        return self._load(self.memory_json)

    def set_memory(self, value: Any) -> None:
        self.memory_json = self._dump(value)

    def get_findings(self) -> list[Any]:
        data = self._load(self.findings_json)
        return data if isinstance(data, list) else []

    def set_findings(self, value: list[Any]) -> None:
        self.findings_json = self._dump(value)

    def get_verification(self) -> Any:
        return self._load(self.verification_json)

    def set_verification(self, value: Any) -> None:
        self.verification_json = self._dump(value)
