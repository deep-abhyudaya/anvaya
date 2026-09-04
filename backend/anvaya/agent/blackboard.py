"""Blackboard state for adaptive agent execution.

The blackboard is a compact, execution-local working memory that lives inside
``ExecutionContext``. It stores facts, hypotheses, evidence references,
contradictions, open questions, and the current next-best-action without
duplicating the domain database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Hypothesis(BaseModel):
    """A testable claim with evidence and confidence."""

    id: str
    statement: str
    confidence: float = 0.0
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    status: str = "proposed"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    next_test: str = ""
    entity_id: str = ""

    def update_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_evidence_for(self, ref: str) -> None:
        if ref not in self.evidence_for:
            self.evidence_for.append(ref)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_evidence_against(self, ref: str) -> None:
        if ref not in self.evidence_against:
            self.evidence_against.append(ref)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def assess(self, confidence: float, status: str = "") -> None:
        self.confidence = max(0.0, min(1.0, round(confidence, 4)))
        if status:
            self.status = status
        self.updated_at = datetime.now(timezone.utc).isoformat()


class Blackboard(BaseModel):
    """Compact, execution-local working state for the agent."""

    goal: str = ""
    facts: dict[str, str] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    completed_actions: list[str] = Field(default_factory=list)
    failed_actions: list[str] = Field(default_factory=list)
    current_candidate: str = ""
    current_entity: str = ""
    current_incident: str = ""
    next_best_action: str = ""
    confidence: float = 0.0
    summary: str = ""
    artifact_state: dict[str, str] = Field(default_factory=dict)
    scope_constraints: list[str] = Field(default_factory=list)

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        existing = self.get_hypothesis(hypothesis.id)
        if existing:
            existing.statement = hypothesis.statement
            existing.assess(hypothesis.confidence, hypothesis.status)
            existing.evidence_for = hypothesis.evidence_for
            existing.evidence_against = hypothesis.evidence_against
            existing.unknowns = hypothesis.unknowns
            existing.next_test = hypothesis.next_test
        else:
            self.hypotheses.append(hypothesis)

    def remove_hypothesis(self, hypothesis_id: str) -> None:
        self.hypotheses = [h for h in self.hypotheses if h.id != hypothesis_id]

    def add_fact(self, key: str, value: str) -> None:
        self.facts[key] = value

    def add_evidence(self, ref: str, summary: str = "", tool: str = "") -> None:
        entry = {"ref": ref, "summary": summary, "tool": tool, "timestamp": datetime.now(timezone.utc).isoformat()}
        if not any(e.get("ref") == ref for e in self.evidence):
            self.evidence.append(entry)

    def add_completed_action(self, action: str) -> None:
        if action not in self.completed_actions:
            self.completed_actions.append(action)

    def add_failed_action(self, action: str, reason: str = "") -> None:
        entry = f"{action}: {reason}" if reason else action
        if entry not in self.failed_actions:
            self.failed_actions.append(entry)

    def update_artifact_state(self, artifact_type: str, status: str) -> None:
        """Update the generation status of an artifact type.
        
        Status should be one of: pending, generating, saved, verified, failed.
        """
        self.artifact_state[artifact_type] = status

    def top_hypothesis(self) -> Hypothesis | None:
        active = [h for h in self.hypotheses if h.status in ("proposed", "testing", "supported")]
        if not active:
            return None
        return max(active, key=lambda h: h.confidence)

    def to_context(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_context(cls, data: dict[str, Any] | None) -> "Blackboard":
        if not data:
            return cls()
        return cls(**data)
