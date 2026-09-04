"""Agent memory: working, episodic, semantic, procedural.

Memory is built over existing ``Execution`` and domain records. It does not
introduce a separate memory database; it retrieves compact, relevant facts and
patterns at decision time.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution


class MemoryStore:
    """Retrieve relevant memory for the current execution."""

    def __init__(self, session: Session):
        self.session = session

    def recall(
        self,
        execution_id: str,
        entity_id: str = "",
        project_id: str = "",
        incident_id: str = "",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Return a compact memory bundle for the current execution."""
        return {
            "working": self._working_memory(execution_id),
            "episodic": self._episodic_memory(entity_id, project_id, incident_id, limit),
            "semantic": self._semantic_memory(project_id, incident_id),
            "procedural": self._procedural_memory(execution_id),
        }

    def _working_memory(self, execution_id: str) -> dict[str, Any]:
        context = self.session.exec(
            select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
        ).first()
        if not context:
            return {"found": False}
        return {
            "found": True,
            "objective": context.objective,
            "plan_summary": [s.get("tool") for s in context.plan],
            "observation_count": len(context.observations),
            "reasoning_summary": context.reasoning_summary,
            "current_action": context.current_action,
        }

    def _episodic_memory(
        self,
        entity_id: str,
        project_id: str,
        incident_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Recall prior executions targeting the same entity/project/incident."""
        stmt = select(Execution).order_by(Execution.started_at.desc())
        if entity_id:
            stmt = stmt.where(
                (Execution.objective.like(f"%{entity_id}%"))
                | (Execution.incident_id == entity_id)
            )
        elif incident_id:
            stmt = stmt.where(Execution.incident_id == incident_id)
        elif project_id:
            stmt = stmt.where(Execution.incident_id.like(f"%{project_id}%"))

        rows = self.session.exec(stmt.limit(limit * 2)).all()
        results = []
        seen: set[str] = set()
        for r in rows:
            if r.execution_id in seen or r.status not in ("completed", "failed"):
                continue
            seen.add(r.execution_id)
            results.append(
                {
                    "execution_id": r.execution_id,
                    "objective": r.objective,
                    "status": r.status,
                    "result_summary": r.result_summary,
                    "started_at": r.started_at.isoformat() if r.started_at else "",
                }
            )
            if len(results) >= limit:
                break
        return results

    def _semantic_memory(self, project_id: str, incident_id: str) -> dict[str, Any]:
        """Return durable facts already persisted by ANVAYA."""
        facts: dict[str, Any] = {"project_id": project_id, "incident_id": incident_id}

        if incident_id:
            from anvaya.models.incident import Incident

            incident = self.session.exec(
                select(Incident).where(Incident.incident_id == incident_id)
            ).first()
            if incident:
                facts["incident"] = {
                    "title": incident.title,
                    "severity": incident.severity,
                    "attack_family": incident.attack_family or "",
                    "status": incident.status.value if incident.status else "",
                    "risk_score": incident.risk_score or 0.0,
                }

        if project_id:
            from anvaya.models.project import Dataset, Project

            project = self.session.exec(
                select(Project).where(Project.project_id == project_id)
            ).first()
            if project:
                facts["project"] = {"name": project.name, "organization_id": project.organization_id}

            dataset = self.session.exec(
                select(Dataset)
                .where(Dataset.project_id == project_id, Dataset.status == "ready")
                .order_by(Dataset.created_at.desc())
            ).first()
            if dataset:
                facts["dataset"] = {
                    "dataset_id": dataset.dataset_id,
                    "filename": dataset.filename,
                    "checksum": dataset.checksum,
                    "size": dataset.size,
                }

        return facts

    def _procedural_memory(self, execution_id: str) -> list[dict[str, Any]]:
        """Extract successful investigation patterns from the current execution."""
        context = self.session.exec(
            select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
        ).first()
        if not context:
            return []
        completed = [s for s in context.plan if s.get("status") == "completed"]
        if not completed:
            return []
        return [
            {
                "pattern": " -> ".join(s.get("tool", "") for s in completed),
                "completed_count": len(completed),
                "objective": context.objective,
            }
        ]
