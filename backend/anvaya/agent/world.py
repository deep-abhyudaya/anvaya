"""Environment observation for the agent.

The world observer queries existing persisted ANVAYA state and returns compact,
typed summaries suitable for model context. It does not duplicate domain data.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from anvaya.models.audit import AuditRecord
from anvaya.models.detection import DetectionRun
from anvaya.models.execution import Execution
from anvaya.models.graph import GraphEdge, GraphNode
from anvaya.models.incident import Incident
from anvaya.models.project import Dataset, Project, ProjectArtifact
from anvaya.models.telemetry import TelemetryEvent


class WorldObserver:
    """Build compact observation snapshots from existing records."""

    def __init__(self, session: Session):
        self.session = session

    def observe_environment(
        self,
        project_id: str = "",
        incident_id: str = "",
        dataset_id: str = "",
    ) -> dict[str, Any]:
        """Return a compact summary of the observable environment."""
        observation: dict[str, Any] = {
            "project_id": project_id,
            "incident_id": incident_id,
            "dataset_id": dataset_id,
        }

        if project_id:
            observation["project"] = self._project_summary(project_id)

        if incident_id:
            observation["incident"] = self._incident_summary(incident_id)
            observation["telemetry"] = self._telemetry_summary(incident_id)
            observation["detections"] = self._detection_summary(incident_id)
            observation["graph"] = self._graph_summary(incident_id)
            observation["blast_radius"] = self._blast_summary(incident_id)
            observation["audit"] = self._audit_summary(incident_id)

        if dataset_id:
            observation["dataset"] = self._dataset_summary(dataset_id)
        elif project_id:
            observation["dataset"] = self._latest_dataset_summary(project_id)

        observation["previous_executions"] = self._previous_executions(project_id, incident_id)
        observation["artifacts"] = self._artifact_summary(project_id)

        return observation

    def _project_summary(self, project_id: str) -> dict[str, Any]:
        project = self.session.exec(select(Project).where(Project.project_id == project_id)).first()
        if not project:
            return {"found": False}
        return {
            "found": True,
            "project_id": project.project_id,
            "name": project.name,
            "organization_id": project.organization_id,
            "description": project.description,
        }

    def _incident_summary(self, incident_id: str) -> dict[str, Any]:
        incident = self.session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()
        if not incident:
            return {"found": False}
        return {
            "found": True,
            "incident_id": incident.incident_id,
            "title": incident.title,
            "severity": incident.severity,
            "status": incident.status.value if incident.status else "",
            "self_correction_status": incident.self_correction_status.value
            if incident.self_correction_status
            else "",
            "attack_family": incident.attack_family or "",
            "risk_score": incident.risk_score or 0.0,
            "blast_radius_score": incident.blast_radius_score or 0.0,
            "whatif_risk_delta": incident.whatif_risk_delta or 0.0,
            "scenario_id": incident.scenario_id or "",
        }

    def _telemetry_summary(self, incident_id: str) -> dict[str, Any]:
        incident = self.session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()
        if not incident:
            return {"found": False}

        events = self.session.exec(
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
        ).all()

        attack = [e for e in events if e.is_attack]
        sources = {e.source for e in events if e.source}
        users = {e.actor for e in events if e.actor}

        return {
            "found": True,
            "total_events": len(events),
            "attack_events": len(attack),
            "unique_sources": len(sources),
            "unique_users": len(users),
            "sources": sorted(sources)[:10],
            "users": sorted(users)[:10],
            "event_ids": [e.event_id for e in events[:10]],
        }

    def _detection_summary(self, incident_id: str) -> dict[str, Any]:
        run = self.session.exec(
            select(DetectionRun)
            .where(DetectionRun.incident_id == incident_id)
            .order_by(DetectionRun.started_at.desc())
        ).first()
        if not run:
            return {"found": False}
        return {
            "found": True,
            "run_id": run.run_id,
            "detected": run.detected,
            "events_processed": run.events_processed,
            "started_at": run.started_at.isoformat() if run.started_at else "",
        }

    def _graph_summary(self, incident_id: str) -> dict[str, Any]:
        nodes = self.session.exec(
            select(GraphNode).where(GraphNode.incident_id == incident_id)
        ).all()
        edges = self.session.exec(
            select(GraphEdge).where(GraphEdge.incident_id == incident_id)
        ).all()
        return {
            "found": bool(nodes),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "compromised": [n.node_id for n in nodes if n.is_compromised][:10],
            "critical": [n.node_id for n in nodes if n.is_critical][:10],
            "highest_impact": sorted(
                [(n.node_id, n.impact_score) for n in nodes if n.impact_score],
                key=lambda x: x[1],
                reverse=True,
            )[:5],
        }

    def _blast_summary(self, incident_id: str) -> dict[str, Any]:
        from anvaya.models.graph import BlastRadiusResult

        blast = self.session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)
        ).first()
        if not blast:
            return {"found": False}
        return {
            "found": True,
            "impact_score": blast.impact_score,
            "total_reachable": blast.total_reachable,
            "compromised_count": blast.compromised_count,
        }

    def _audit_summary(self, incident_id: str) -> dict[str, Any]:
        records = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident_id)
            .order_by(AuditRecord.timestamp.desc())
            .limit(10)
        ).all()
        return {
            "found": bool(records),
            "record_count": len(records),
            "latest_actions": [r.action for r in records[:5]],
        }

    def _dataset_summary(self, dataset_id: str) -> dict[str, Any]:
        dataset = self.session.exec(select(Dataset).where(Dataset.dataset_id == dataset_id)).first()
        if not dataset:
            return {"found": False}
        return {
            "found": True,
            "dataset_id": dataset.dataset_id,
            "filename": dataset.filename,
            "checksum": dataset.checksum,
            "status": dataset.status,
            "size": dataset.size,
        }

    def _latest_dataset_summary(self, project_id: str) -> dict[str, Any]:
        dataset = self.session.exec(
            select(Dataset)
            .where(Dataset.project_id == project_id, Dataset.status == "ready")
            .order_by(Dataset.created_at.desc())
        ).first()
        if not dataset:
            return {"found": False}
        return self._dataset_summary(dataset.dataset_id)

    def _previous_executions(self, project_id: str, incident_id: str) -> list[dict[str, Any]]:
        stmt = select(Execution).order_by(Execution.started_at.desc()).limit(10)
        if incident_id:
            stmt = stmt.where(Execution.incident_id == incident_id)
        elif project_id:
            stmt = stmt.where(Execution.incident_id.like(f"%{project_id}%"))
        rows = self.session.exec(stmt).all()
        return [
            {
                "execution_id": r.execution_id,
                "objective": r.objective,
                "status": r.status,
                "result_summary": r.result_summary,
                "started_at": r.started_at.isoformat() if r.started_at else "",
            }
            for r in rows
        ]

    def _artifact_summary(self, project_id: str) -> dict[str, Any]:
        if not project_id:
            return {"found": False}
        artifacts = self.session.exec(
            select(ProjectArtifact)
            .where(ProjectArtifact.project_id == project_id)
            .order_by(ProjectArtifact.created_at.desc())
        ).all()
        by_type: dict[str, int] = {}
        for a in artifacts:
            by_type[a.artifact_type] = by_type.get(a.artifact_type, 0) + 1
        return {
            "found": bool(artifacts),
            "total": len(artifacts),
            "by_type": by_type,
            "latest_generation_id": artifacts[0].generation_id if artifacts else "",
        }
