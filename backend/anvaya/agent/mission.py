"""Mission state for adaptive agent execution.

A mission is a lightweight layer over the existing ``Execution`` and
``ExecutionContext`` models. It stores the objective, budgets, success/failure
conditions, and current mission state without duplicating execution persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Mission(BaseModel):
    """Runtime mission state carried inside an execution context."""

    objective: str = ""
    success_condition: str = "Find a high-confidence security issue and verify it."
    failure_condition: str = "Evidence exhausted, budget exceeded, or unrecoverable error."

    max_iterations: int = 20
    max_tool_calls: int = 50
    max_model_calls: int = 25
    max_duration_ms: float = 180000.0
    confidence_threshold: float = 0.75

    iteration: int = 0
    tool_calls: int = 0
    model_calls: int = 0

    constraints: list[str] = Field(default_factory=list)
    allowed_artifacts: list[str] = Field(default_factory=list)

    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    stop_reason: str = ""
    status: str = "running"

    project_id: str = ""
    dataset_id: str = ""
    incident_id: str = ""

    def is_within_budget(self) -> bool:
        """Return True if the mission has not exceeded its budgets."""
        if self.iteration >= self.max_iterations:
            return False
        if self.tool_calls >= self.max_tool_calls:
            return False
        if self.model_calls >= self.max_model_calls:
            return False
        now = datetime.now(timezone.utc)
        try:
            started = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        except Exception:
            started = now
        if (now - started).total_seconds() * 1000 >= self.max_duration_ms:
            return False
        return True

    def complete(self, reason: str, status: str = "completed") -> None:
        """Mark the mission as complete with a reason."""
        self.status = status
        self.stop_reason = reason
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def fail(self, reason: str) -> None:
        """Mark the mission as failed with a reason."""
        self.complete(reason, status="failed")

    def step(self) -> None:
        """Increment iteration and tool call counters after a successful step."""
        self.iteration += 1
        self.tool_calls += 1

    def model_step(self) -> None:
        """Increment the model call counter."""
        self.model_calls += 1

    def should_continue(self) -> bool:
        """Check whether the mission should continue iterating."""
        return self.status == "running" and self.is_within_budget()

    def to_context(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_context(cls, data: dict[str, Any] | None) -> "Mission":
        if not data:
            return cls()
        return cls(**data)
