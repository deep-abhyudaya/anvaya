"""Local ANVAYA tool executor.

Each tool wraps existing business logic without duplicating engines.
Results are typed as ToolResult with safe summaries and artifact refs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.agent.adapters import GmailAdapter, N8NAdapter, TavilyAdapter
from anvaya.agent.events import event_store
from anvaya.agent.schemas import ArtifactRef, ToolResult
from anvaya.agent.world import WorldObserver
from anvaya.blastscope import BlastScopeEngine
from anvaya.config import settings
from anvaya.generation import delete_project_artifacts
from anvaya.generations.builder import ArtifactBuilder
from anvaya.live.dispatch import on_incident_event
from anvaya.live.enums import IncidentEventType
from anvaya.logging import get_logger
from anvaya.models.audit import AuditRecord, verify_chain
from anvaya.models.detection import DetectionRun
from anvaya.models.enums import IncidentStatus, SelfCorrectionStatus
from anvaya.models.execution import Execution
from anvaya.models.graph import BlastRadiusResult, GraphEdge, GraphNode
from anvaya.models.incident import Incident
from anvaya.models.project import ARTIFACT_TYPES, Dataset, Generation, GenerationStatus, Project
from anvaya.models.telemetry import TelemetryEvent
from anvaya.sentinel import SentinelEngine
from anvaya.whatif.engine import WhatIfEngine

logger = get_logger("anvaya.agent.executor")


class LocalToolExecutor:
    """Executes tools against real ANVAYA capabilities."""

    def __init__(self, session: Session):
        self.session = session
        self._current_execution_id: str = ""

    def _next_sequence(self) -> int:
        from anvaya.models.execution import ExecutionEvent

        if not self._current_execution_id:
            return 0
        last = self.session.exec(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == self._current_execution_id)
            .order_by(ExecutionEvent.sequence.desc())
        ).first()
        return (last.sequence + 1) if last else 1

    def _emit_artifact_progress(
        self, event_type: str, label: str, payload: dict[str, Any] | None = None
    ) -> None:
        if not self._current_execution_id:
            return
        try:
            event_store.emit(
                self.session,
                self._current_execution_id,
                self._next_sequence(),
                event_type,
                label=label,
                tool_name="manage_artifacts",
                payload=payload or {},
            )
        except Exception:
            pass

    def execute(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        tool_call_id: str = "",
        execution_id: str = "",
    ) -> ToolResult:
        """Execute a tool by name."""
        call_id = tool_call_id or f"call-{uuid4().hex[:8]}"
        started = perf_counter()
        started_at = datetime.now(timezone.utc).isoformat()
        self._current_execution_id = execution_id

        handler = getattr(self, f"handle_{tool_name}", None)
        if handler is None:
            return ToolResult(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="failure",
                provider="anvaya",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=round((perf_counter() - started) * 1000, 2),
                input_summary=_safe_summary(inputs),
                error_code="tool_not_found",
                error_message=f"Tool '{tool_name}' is not implemented by the local executor.",
            )

        try:
            result = handler(inputs)
            result.tool_call_id = call_id
            if not result.started_at:
                result.started_at = started_at
            result.completed_at = datetime.now(timezone.utc).isoformat()
            result.duration_ms = round((perf_counter() - started) * 1000, 2)
            if not result.provider:
                result.provider = "anvaya"
            result.input_summary = _safe_summary(inputs)
            return result
        except Exception as exc:
            logger.warning("local_tool_error", tool=tool_name, error=str(exc))
            return ToolResult(
                tool_call_id=call_id,
                tool_name=tool_name,
                status="failure",
                provider="anvaya",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=round((perf_counter() - started) * 1000, 2),
                input_summary=_safe_summary(inputs),
                error_code="execution_error",
                error_message=str(exc),
            )


    def handle_get_incident(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        return ToolResult(
            tool_name="get_incident",
            status="success",
            output_summary=f"Loaded incident {incident_id} ({incident.title})",
            output=incident.model_dump(),
            artifact_refs=[
                ArtifactRef(
                    ref_type="incident",
                    ref_id=incident_id,
                    label=incident.title,
                    link=f"/incidents/{incident_id}",
                )
            ],
        )

    def handle_get_telemetry(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        limit = int(inputs.get("limit", 100))
        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
            .limit(limit)
        )
        events = list(self.session.exec(stmt).all())
        attack_events = [e for e in events if e.is_attack]
        summary = f"Inspected {len(events)} telemetry events ({len(attack_events)} attack)"

        return ToolResult(
            tool_name="get_telemetry",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "total_events": len(events),
                "attack_events": len(attack_events),
                "events": [e.model_dump() for e in events[:20]],
            },
            artifact_refs=[
                ArtifactRef(
                    ref_type="telemetry",
                    ref_id=incident_id,
                    label=f"{len(events)} telemetry events",
                    link=f"/incidents?incident_id={incident_id}",
                )
            ],
        )

    def handle_inspect_detection(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        stmt = (
            select(DetectionRun)
            .where(DetectionRun.incident_id == incident_id)
            .order_by(DetectionRun.started_at.desc())
        )
        run = self.session.exec(stmt).first()
        if not run:
            return ToolResult(
                tool_name="inspect_detection",
                status="success",
                output_summary="No detection runs recorded for this incident.",
                output={"incident_id": incident_id, "detected": False},
            )

        summary = f"Detection run {run.run_id}: detected={run.detected}"
        summary += f", events={run.events_processed}"

        return ToolResult(
            tool_name="inspect_detection",
            status="success",
            output_summary=summary,
            output=run.model_dump(),
            artifact_refs=[
                ArtifactRef(
                    ref_type="detection",
                    ref_id=run.run_id,
                    label=f"Detection {run.run_id}",
                    link=f"/detections/{run.run_id}",
                )
            ],
        )


    def handle_run_sentinel_trace(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        engine = SentinelEngine(self.session)
        result = engine.backtrack(incident_id)
        if result.get("error"):
            return ToolResult(
                tool_name="run_sentinel_trace",
                status="failure",
                error_code="backtrack_failed",
                error_message=result["error"],
            )

        return ToolResult(
            tool_name="run_sentinel_trace",
            status="success",
            output_summary=f"Backtracked {result.get('evidence_count', 0)} evidence items",
            output=result,
            artifact_refs=[
                ArtifactRef(
                    ref_type="evidence",
                    ref_id=incident_id,
                    label=f"{result.get('evidence_count', 0)} evidence items",
                    link=f"/miss-replay?incident_id={incident_id}",
                )
            ],
        )

    def handle_confirm_ground_truth(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        if incident.self_correction_status == SelfCorrectionStatus.NONE:
            incident.self_correct_to(SelfCorrectionStatus.MISS)
            self._audit(incident, "miss_confirmed", "NONE", "MISS")

        if incident.self_correction_status == SelfCorrectionStatus.MISS:
            incident.self_correct_to(SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED)
            self._audit(incident, "ground_truth_confirmed", "MISS", "GROUND_TRUTH_CONFIRMED")
            self.session.add(incident)
            self.session.commit()

        return ToolResult(
            tool_name="confirm_ground_truth",
            status="success",
            output_summary=f"Ground truth confirmed for {incident_id}",
            output={"incident_id": incident_id, "status": incident.self_correction_status.value},
        )

    def handle_propose_rule(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        engine = SentinelEngine(self.session)
        result = engine.propose_rule(incident_id)
        if result.get("error"):
            return ToolResult(
                tool_name="propose_rule",
                status="failure",
                error_code="propose_failed",
                error_message=result["error"],
            )

        rule_id = result.get("rule_id", "")
        conditions = result.get("conditions", {}).get("conditions", [])
        summary = f"Proposed rule {rule_id} with {len(conditions)} conditions"

        return ToolResult(
            tool_name="propose_rule",
            status="success",
            output_summary=summary,
            output=result,
            artifact_refs=[
                ArtifactRef(
                    ref_type="rule",
                    ref_id=rule_id,
                    label=result.get("rule_name", rule_id),
                    link=f"/rules/{rule_id}",
                )
            ],
        )

    def handle_validate_rule(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        engine = SentinelEngine(self.session)
        result = engine.validate_rule(incident_id)
        if result.get("error"):
            return ToolResult(
                tool_name="validate_rule",
                status="failure",
                error_code="validate_failed",
                error_message=result["error"],
            )

        f1 = result.get("f1_score")
        tp = result.get("tp")
        fp = result.get("fp")
        summary = f"Rule validated: F1={f1}, TP={tp}, FP={fp}"

        return ToolResult(
            tool_name="validate_rule",
            status="success",
            output_summary=summary,
            output=result,
        )

    def handle_run_replay(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        engine = SentinelEngine(self.session)
        result = engine.replay_attack(incident_id)
        if result.get("error"):
            return ToolResult(
                tool_name="run_replay",
                status="failure",
                error_code="replay_failed",
                error_message=result["error"],
            )

        replay_id = result.get("replay_id", "")
        post_patch = result.get("post_patch_detected", False)
        summary = f"Replay {replay_id}: {'CAUGHT' if post_patch else 'MISSED'} post-patch"

        return ToolResult(
            tool_name="run_replay",
            status="success",
            output_summary=summary,
            output=result,
            artifact_refs=[
                ArtifactRef(
                    ref_type="replay",
                    ref_id=replay_id,
                    label=summary,
                    link=f"/miss-replay?incident_id={incident_id}",
                )
            ],
        )


    def handle_run_blastscope(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        engine = BlastScopeEngine(self.session)
        result = engine.run(incident_id)
        if result.get("error"):
            return ToolResult(
                tool_name="run_blastscope",
                status="failure",
                error_code="blastscope_failed",
                error_message=result["error"],
            )

        reachable = result.get("total_reachable", 0)
        impact = result.get("impact_score")
        summary = f"BlastScope: {reachable} reachable, impact={impact}"

        return ToolResult(
            tool_name="run_blastscope",
            status="success",
            output_summary=summary,
            output=result,
            artifact_refs=[
                ArtifactRef(
                    ref_type="blastscope",
                    ref_id=incident_id,
                    label=f"Impact {result.get('impact_score')}",
                    link=f"/threat-ecosystem?incident_id={incident_id}",
                )
            ],
        )

    def handle_build_or_update_ecosystem(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        mode = inputs.get("mode", "CONTAIN")

        engine = BlastScopeEngine(self.session)
        graph_result = engine.run(incident_id)

        from anvaya.routers.simulation import get_ecosystem

        step = int(inputs.get("step", 0))
        ecosystem = get_ecosystem(
            mode=mode,
            step=step,
            project_id="",
            session=self.session,
        )

        if graph_result.get("error"):
            graph_result = {}

        node_count = len(ecosystem.get("nodes", []))
        health = ecosystem.get("health")
        summary = f"Ecosystem: {node_count} nodes, health={health}%"

        return ToolResult(
            tool_name="build_or_update_ecosystem",
            status="success",
            output_summary=summary,
            output={"graph": graph_result, "ecosystem": ecosystem},
            artifact_refs=[
                ArtifactRef(
                    ref_type="ecosystem",
                    ref_id=incident_id,
                    label=f"Health {ecosystem.get('health')}%",
                    link=f"/threat-ecosystem?incident_id={incident_id}&mode={mode}",
                )
            ],
        )

    def handle_run_orbit_analysis(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        blast = self.session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)
        ).first()
        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        orbit = {
            "incident_id": incident_id,
            "risk_score": incident.risk_score or 0.0,
            "blast_radius_score": incident.blast_radius_score
            or (blast.impact_score if blast else 0.0),
            "whatif_risk_delta": incident.whatif_risk_delta,
            "severity": incident.severity,
            "engines": {
                "sentinel": 1.0
                if incident.self_correction_status == SelfCorrectionStatus.CAUGHT
                else 0.0,
                "blastscope": incident.blast_radius_score or 0.0,
                "whatif": incident.whatif_risk_delta,
                "ledger": 1.0 if incident.status == IncidentStatus.SEALED else 0.0,
            },
            "note": "Orbit analysis derived from persisted engine results.",
        }

        risk = orbit["risk_score"]
        blast = orbit["blast_radius_score"]
        summary = f"Orbit: risk={risk:.2f}, blast={blast:.2f}"

        return ToolResult(
            tool_name="run_orbit_analysis",
            status="success",
            output_summary=summary,
            output=orbit,
            artifact_refs=[
                ArtifactRef(
                    ref_type="orbit",
                    ref_id=incident_id,
                    label=f"Risk {orbit['risk_score']:.2f}",
                    link=f"/risk-orbits?incident_id={incident_id}",
                )
            ],
        )

    def handle_run_reachability(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        blast = self.session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)
        ).first()
        if not blast:
            return _not_found("blast radius", incident_id)

        nodes = self.session.exec(
            select(GraphNode).where(GraphNode.incident_id == incident_id)
        ).all()
        edges = self.session.exec(
            select(GraphEdge).where(GraphEdge.incident_id == incident_id)
        ).all()

        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.source_node_id].append(edge.target_node_id)

        items = []
        for node in nodes:
            if node.is_compromised:
                state = "COMPROMISED"
            elif node.is_critical:
                state = "CRITICAL"
            else:
                state = "REACHABLE"
            items.append(
                {
                    "id": node.node_id,
                    "name": node.label,
                    "state": state,
                    "hops": node.depth,
                    "attackScore": round(node.impact_score, 2),
                    "defenseScore": round(max(0.0, 1.0 - node.impact_score), 2),
                    "adjacent": adjacency.get(node.node_id, []),
                    "reachable_count": len(adjacency.get(node.node_id, [])),
                }
            )

        reachability = {"items": items, "incident_id": incident_id}
        summary = f"Reachability: {len(items)} assets"

        return ToolResult(
            tool_name="run_reachability",
            status="success",
            output_summary=summary,
            output=reachability,
            artifact_refs=[
                ArtifactRef(
                    ref_type="reachability",
                    ref_id=incident_id,
                    label=f"{len(items)} assets",
                    link=f"/reach-board?incident_id={incident_id}",
                )
            ],
        )

    def handle_run_segment_analysis(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        blast = self.session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)
        ).first()
        if not blast:
            return _not_found("blast radius", incident_id)

        paths = json.loads(blast.propagation_paths_json or "[]")
        nodes = self.session.exec(
            select(GraphNode).where(GraphNode.incident_id == incident_id)
        ).all()
        prefix = f"{incident_id}-"
        node_map = {n.node_id.removeprefix(prefix): n for n in nodes}

        items = []
        rank = 1
        for path in paths:
            for i in range(len(path) - 1):
                src = path[i]
                dst = path[i + 1]
                dst_node = node_map.get(dst)
                if dst_node is None:
                    continue

                if dst_node.is_compromised:
                    risk = "critical"
                elif dst_node.is_critical:
                    risk = "high"
                elif dst_node.impact_score >= 0.6:
                    risk = "medium"
                else:
                    risk = "low"

                traffic = round(min(max(dst_node.impact_score, 0.1), 0.95), 2)
                items.append(
                    {
                        "id": f"SEG-{rank:03d}",
                        "from": src,
                        "to": dst,
                        "rank": rank,
                        "depth": i + 1,
                        "reach": len(path) - i - 1,
                        "traffic": traffic,
                        "risk": risk,
                        "neutralized": dst_node.state == "neutralized",
                    }
                )
                rank += 1

        segments = {"items": items, "incident_id": incident_id, "nodes": [], "extra_edges": []}

        return ToolResult(
            tool_name="run_segment_analysis",
            status="success",
            output_summary=f"Segments: {len(items)} ranked segments",
            output=segments,
            artifact_refs=[
                ArtifactRef(
                    ref_type="segments",
                    ref_id=incident_id,
                    label=f"{len(items)} segments",
                    link=f"/segments?incident_id={incident_id}",
                )
            ],
        )


    def handle_run_what_if(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        changes = inputs.get("changes", {"is_off_hours": 0.0, "is_new_device": 0.0})
        engine = WhatIfEngine(self.session)
        result = engine.analyze(incident_id, changes)
        if result.get("error"):
            return ToolResult(
                tool_name="run_what_if",
                status="failure",
                error_code="whatif_failed",
                error_message=result["error"],
            )

        orig = result.get("original_score", 0)
        cf = result.get("counterfactual_score", 0)
        delta = result.get("score_delta", 0)
        summary = f"What-If: original={orig:.4f}, counterfactual={cf:.4f}, delta={delta:.4f}"

        return ToolResult(
            tool_name="run_what_if",
            status="success",
            output_summary=summary,
            output=result,
            artifact_refs=[
                ArtifactRef(
                    ref_type="what_if",
                    ref_id=result.get("analysis_id", ""),
                    label=f"Delta {result.get('score_delta', 0):.4f}",
                    link=f"/risk-orbits?incident_id={incident_id}",
                )
            ],
        )


    def handle_get_metrics(self, inputs: dict[str, Any]) -> ToolResult:
        from anvaya.routers.metrics import get_metrics

        result = get_metrics(self.session)

        total = result.get("total_incidents", 0)
        caught = result.get("caught_replays", 0)
        summary = f"Metrics: {total} incidents, {caught} caught replays"

        return ToolResult(
            tool_name="get_metrics",
            status="success",
            output_summary=summary,
            output=result,
        )

    def handle_append_audit_record(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        last = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident_id)
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        prev_hash = last.record_hash if last else ""

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            actor="agent",
            action=inputs.get("action", "agent_action"),
            previous_state=inputs.get("previous_state", ""),
            new_state=inputs.get("new_state", ""),
            reason=inputs.get("reason", "Agent execution step"),
            control_mapping=inputs.get("control_mapping", "NIST.RESPOND.AUDIT"),
            result="success",
        )
        record.compute_hash(prev_hash)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)

        return ToolResult(
            tool_name="append_audit_record",
            status="success",
            output_summary=f"Appended audit record {record.record_id} to {incident_id}",
            output=record.model_dump(),
            artifact_refs=[
                ArtifactRef(
                    ref_type="audit",
                    ref_id=record.record_id,
                    label=record.action,
                    link=f"/ledger?incident_id={incident_id}",
                )
            ],
        )

    def handle_generate_artifacts(self, inputs: dict[str, Any]) -> ToolResult:
        """Generate project artifacts through the staged artifact builder.

        Delegates to `handle_manage_artifacts` so the same streaming,
        per-artifact construction experience is used regardless of whether the
        agent calls `manage_artifacts` or `generate_artifacts`.
        """
        result = self.handle_manage_artifacts(
            {
                "project_id": inputs.get("project_id", ""),
                "action": "generate",
                "requested_artifacts": inputs.get("requested_artifacts", ["orbits"]),
                "dataset_id": inputs.get("dataset_id", ""),
            }
        )
        result.tool_name = "generate_artifacts"
        return result

    def handle_manage_artifacts(self, inputs: dict[str, Any]) -> ToolResult:
        """Full lifecycle: generate, regenerate, or delete project artifacts."""
        project_id = inputs.get("project_id", "")
        action = inputs.get("action", "generate")
        requested = inputs.get("requested_artifacts", ["orbits"])
        dataset_id = inputs.get("dataset_id", "")

        if not project_id:
            return _invalid("project_id is required")

        project = self.session.exec(select(Project).where(Project.project_id == project_id)).first()
        if not project:
            return _not_found("project", project_id)

        if requested == ["all"] or requested == "all" or "all" in requested:
            requested = list(ARTIFACT_TYPES)
        if not isinstance(requested, list) or not requested:
            return _invalid("requested_artifacts must be a non-empty list")

        artifact_types = [r for r in requested if r in ARTIFACT_TYPES]
        if not artifact_types:
            return _invalid(f"No valid artifact types in {requested}")

        if action == "delete":
            self._emit_artifact_progress(
                "artifact.deleted",
                f"Deleting {artifact_types} artifacts",
                {"project_id": project_id, "artifact_types": artifact_types},
            )
            deleted = delete_project_artifacts(
                self.session, project_id, artifact_types, delete_generations=True
            )
            self._emit_artifact_progress(
                "artifact.deleted",
                f"Deleted {deleted} {artifact_types} artifact(s)",
                {"project_id": project_id, "artifact_types": artifact_types, "deleted": deleted},
            )
            return ToolResult(
                tool_name="manage_artifacts",
                status="success",
                output_summary=f"Deleted {deleted} {artifact_types} artifact(s) for {project_id}",
                output={"deleted": deleted, "project_id": project_id, "types": artifact_types},
                artifact_refs=[
                    ArtifactRef(
                        ref_type="project",
                        ref_id=project_id,
                        label=f"Project {project.name} artifacts deleted",
                        link=f"/projects/{project_id}",
                    )
                ],
            )

        if action in ("generate", "regenerate"):
            if action == "regenerate":
                self._emit_artifact_progress(
                    "artifact.regenerating",
                    f"Regenerating {artifact_types}",
                    {"project_id": project_id, "artifact_types": artifact_types},
                )
                delete_project_artifacts(
                    self.session, project_id, artifact_types, delete_generations=True
                )

            dataset = None
            if dataset_id:
                dataset = self.session.exec(
                    select(Dataset).where(
                        Dataset.dataset_id == dataset_id,
                        Dataset.project_id == project_id,
                    )
                ).first()
            if not dataset:
                dataset = self.session.exec(
                    select(Dataset)
                    .where(Dataset.project_id == project_id, Dataset.status == "ready")
                    .order_by(Dataset.created_at.desc())
                ).first()

            if not dataset:
                return ToolResult(
                    tool_name="manage_artifacts",
                    status="failure",
                    error_code="no_dataset",
                    error_message="No usable dataset found for the project",
                )

            if not self._current_execution_id:
                return ToolResult(
                    tool_name="manage_artifacts",
                    status="failure",
                    error_code="no_execution",
                    error_message="No active execution to stream the artifact build",
                )

            execution = self.session.exec(
                select(Execution).where(Execution.execution_id == self._current_execution_id)
            ).first()
            if not execution:
                execution = Execution(
                    execution_id=self._current_execution_id,
                    objective="Artifact generation",
                    status="running",
                    provider="anvaya",
                )
                self.session.add(execution)
                self.session.commit()

            created: dict[str, int] = {}
            last_generation_id = ""

            self._emit_artifact_progress(
                "artifact.generating",
                f"Generating {artifact_types}",
                {
                    "project_id": project_id,
                    "artifact_types": artifact_types,
                    "dataset_id": dataset.dataset_id,
                },
            )

            for atype in artifact_types:
                generation = Generation(
                    generation_id=f"GEN-{uuid4().hex[:8].upper()}",
                    organization_id=project.organization_id,
                    project_id=project_id,
                    dataset_id=dataset.dataset_id,
                    user_id="agent",
                    prompt=f"Make {atype.title()}",
                    target_artifact_type=atype,
                    requested_artifacts_json=json.dumps([atype]),
                    created_artifacts_json="{}",
                    status=GenerationStatus.PENDING,
                )
                self.session.add(generation)
                self.session.commit()
                self.session.refresh(generation)

                builder = ArtifactBuilder(
                    self.session,
                    generation,
                    execution,
                    project,
                )
                try:
                    result = builder.run()
                except Exception as exc:
                    logger.error(
                        "artifact_build_failed",
                        project_id=project_id,
                        artifact_type=atype,
                        error=str(exc),
                    )
                    result = {"status": "failed", "error": str(exc)}

                if result.get("status") != "completed":
                    return ToolResult(
                        tool_name="manage_artifacts",
                        status="failure",
                        error_code="generation_failed",
                        error_message=result.get("error", f"{atype} build failed"),
                    )

                created[atype] = result.get("total_artifacts", 1)
                last_generation_id = result.get("generation_id", generation.generation_id)

            self._emit_artifact_progress(
                "agent.artifact_action_complete",
                f"Artifact action complete: {action}",
                {
                    "project_id": project_id,
                    "artifact_types": artifact_types,
                    "action": action,
                    "created": created,
                },
            )

            artifact_refs = [
                ArtifactRef(
                    ref_type=atype,
                    ref_id=f"{last_generation_id}-{atype}",
                    label=f"{atype}: {count} created",
                    link=f"/projects/{project_id}",
                )
                for atype, count in created.items()
                if count
            ]

            return ToolResult(
                tool_name="manage_artifacts",
                status="success",
                output_summary=(
                    f"{'Regenerated' if action == 'regenerate' else 'Generated'}"
                    f" {len([c for c in created.values() if c])} "
                    f"artifact types from {dataset.filename}"
                ),
                output={"created": created, "generation_id": last_generation_id},
                artifact_refs=artifact_refs,
            )

        return _invalid(f"Unknown action: {action}")

    def handle_verify_audit_chain(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs.get("incident_id", "")
        if incident_id:
            records = list(
                self.session.exec(
                    select(AuditRecord)
                    .where(AuditRecord.incident_id == incident_id)
                    .order_by(AuditRecord.timestamp.asc())
                ).all()
            )
            valid = verify_chain(records)
            result = {"incident_id": incident_id, "valid": valid, "record_count": len(records)}
            summary = f"Incident {incident_id} audit chain valid={valid} ({len(records)} records)"
        else:
            from anvaya.routers.audit import verify_audit_chain

            result = verify_audit_chain(self.session)
            summary = (
                f"Global audit verification: valid={result.get('valid')} "
                f"({result.get('record_count')} records)"
            )

        return ToolResult(
            tool_name="verify_audit_chain",
            status="success",
            output_summary=summary,
            output=result,
        )

    def handle_seal_incident(self, inputs: dict[str, Any]) -> ToolResult:
        incident_id = inputs["incident_id"]
        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        if incident.status == IncidentStatus.SEALED:
            return ToolResult(
                tool_name="seal_incident",
                status="success",
                output_summary=f"Incident {incident_id} is already sealed",
                output={"incident_id": incident_id, "status": incident.status.value},
            )

        try:
            if incident.status != IncidentStatus.ANALYZED:
                incident.transition_to(IncidentStatus.ANALYZED)
            if incident.status != IncidentStatus.SIMULATED:
                incident.transition_to(IncidentStatus.SIMULATED)
            if incident.status != IncidentStatus.EXPLAINED:
                incident.transition_to(IncidentStatus.EXPLAINED)
            if incident.status != IncidentStatus.SEALED:
                incident.transition_to(IncidentStatus.SEALED)
        except ValueError as exc:
            return ToolResult(
                tool_name="seal_incident",
                status="failure",
                error_code="invalid_transition",
                error_message=str(exc),
            )

        self.session.add(incident)

        last = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident_id)
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        prev_hash = last.record_hash if last else ""

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            actor="agent",
            action="incident_sealed",
            previous_state="explained",
            new_state="sealed",
            reason="Agentic investigation complete",
            control_mapping="NIST.RESPOND.SEAL",
            result="success",
        )
        record.compute_hash(prev_hash)
        self.session.add(record)
        self.session.commit()

        on_incident_event(incident, IncidentEventType.SEALED, self.session)

        return ToolResult(
            tool_name="seal_incident",
            status="success",
            output_summary=f"Incident {incident_id} sealed",
            output={"incident_id": incident_id, "status": incident.status.value},
            artifact_refs=[
                ArtifactRef(
                    ref_type="incident",
                    ref_id=incident_id,
                    label="Sealed",
                    link=f"/ledger?incident_id={incident_id}",
                )
            ],
        )


    def handle_observe_environment(self, inputs: dict[str, Any]) -> ToolResult:
        """Return a compact observation of the environment."""
        incident_id = inputs.get("incident_id", "")
        project_id = inputs.get("project_id", "")
        objective = inputs.get("objective", "")

        if not incident_id and not project_id and objective:
            import re

            match = re.search(r"\b(INC-[A-Z0-9-]+)\b", objective, re.IGNORECASE)
            if match:
                incident_id = match.group(1).upper()
            match = re.search(r"\b(PRJ-[A-Z0-9-]+)\b", objective, re.IGNORECASE)
            if match:
                project_id = match.group(1).upper()

        observer = WorldObserver(self.session)
        observation = observer.observe_environment(
            project_id=project_id, incident_id=incident_id, dataset_id=""
        )

        summary = "Environment: "
        parts = []
        if observation.get("incident", {}).get("found"):
            parts.append(f"incident {observation['incident']['incident_id']}")
        if observation.get("project", {}).get("found"):
            parts.append(f"project {observation['project']['project_id']}")
        if observation.get("telemetry", {}).get("found"):
            parts.append(f"{observation['telemetry']['total_events']} events")
        if observation.get("graph", {}).get("found"):
            parts.append(f"{observation['graph']['node_count']} graph nodes")
        summary += ", ".join(parts) if parts else "empty environment"

        return ToolResult(
            tool_name="observe_environment",
            status="success",
            output_summary=summary,
            output=observation,
        )

    def handle_observe_project(self, inputs: dict[str, Any]) -> ToolResult:
        """Return a compact observation of a project."""
        project_id = inputs.get("project_id", "")
        if not project_id:
            return _invalid("project_id is required")

        observer = WorldObserver(self.session)
        observation = observer.observe_environment(
            project_id=project_id, incident_id="", dataset_id=""
        )

        summary = f"Project {project_id}: "
        parts = []
        if observation.get("project", {}).get("found"):
            parts.append(observation["project"].get("name", ""))
        if observation.get("dataset", {}).get("found"):
            parts.append(f"dataset {observation['dataset']['dataset_id']}")
        if observation.get("artifacts", {}).get("found"):
            parts.append(f"{observation['artifacts']['total']} artifacts")
        if observation.get("previous_executions"):
            parts.append(f"{len(observation['previous_executions'])} prior executions")
        summary += ", ".join(parts) if parts else "no project data"

        return ToolResult(
            tool_name="observe_project",
            status="success",
            output_summary=summary,
            output=observation,
        )

    def handle_detect_anomalies(self, inputs: dict[str, Any]) -> ToolResult:
        """Detect anomalous entities for an incident or project."""
        incident_id = inputs.get("incident_id", "")
        project_id = inputs.get("project_id", "")
        top_k = int(inputs.get("top_k", 5))

        observer = WorldObserver(self.session)
        observation = observer.observe_environment(
            project_id=project_id, incident_id=incident_id, dataset_id=""
        )

        telemetry = observation.get("telemetry", {})
        total = telemetry.get("total_events", 0)
        attack = telemetry.get("attack_events", 0)
        sources = telemetry.get("sources", [])
        users = telemetry.get("users", [])

        attack_ratio = attack / max(total, 1)
        candidates: list[dict[str, Any]] = []
        for i, src in enumerate(sources[:top_k]):
            score = min(0.95, 0.2 + attack_ratio + (0.05 * (top_k - i)))
            candidates.append(
                {
                    "entity_id": src,
                    "type": "host",
                    "score": round(score, 3),
                    "reason": "source host with anomalous activity",
                }
            )
        for i, user in enumerate(users[:top_k]):
            if not any(c["entity_id"] == user for c in candidates):
                score = min(0.9, 0.15 + attack_ratio + (0.03 * (top_k - i)))
                candidates.append(
                    {
                        "entity_id": user,
                        "type": "user",
                        "score": round(score, 3),
                        "reason": "user with anomalous activity",
                    }
                )

        candidates.sort(key=lambda c: c["score"], reverse=True)

        summary = f"Detected {len(candidates)} anomaly candidates"
        if candidates:
            summary += f"; top: {candidates[0]['entity_id']} (score {candidates[0]['score']})"

        return ToolResult(
            tool_name="detect_anomalies",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "project_id": project_id,
                "total_events": total,
                "attack_events": attack,
                "candidates": candidates,
            },
        )

    def handle_search_events(self, inputs: dict[str, Any]) -> ToolResult:
        """Search telemetry events for an entity or incident."""
        incident_id = inputs.get("incident_id", "")
        entity_id = inputs.get("entity_id", "")
        limit = int(inputs.get("limit", 50))

        if not incident_id:
            return _invalid("incident_id is required")

        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
            .limit(limit)
        )
        if entity_id:
            stmt = stmt.where(
                (TelemetryEvent.source == entity_id)
                | (TelemetryEvent.destination == entity_id)
                | (TelemetryEvent.actor == entity_id)
            )

        events = list(self.session.exec(stmt).all())
        summary = f"Found {len(events)} events" + (f" for {entity_id}" if entity_id else "")

        return ToolResult(
            tool_name="search_events",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "entity_id": entity_id,
                "count": len(events),
                "events": [e.model_dump() for e in events[:20]],
            },
        )

    def handle_search_entities(self, inputs: dict[str, Any]) -> ToolResult:
        """Search graph/telemetry entities for an incident."""
        incident_id = inputs.get("incident_id", "")
        query = inputs.get("query", "")

        if not incident_id:
            return _invalid("incident_id is required")

        nodes = self.session.exec(
            select(GraphNode)
            .where(GraphNode.incident_id == incident_id)
            .order_by(GraphNode.impact_score.desc())
        ).all()

        matched = []
        for n in nodes:
            if (
                query
                and query.lower() not in n.label.lower()
                and query.lower() not in n.node_id.lower()
            ):
                continue
            matched.append(
                {
                    "node_id": n.node_id,
                    "label": n.label,
                    "type": n.node_type,
                    "impact_score": n.impact_score,
                    "is_compromised": n.is_compromised,
                    "is_critical": n.is_critical,
                }
            )

        summary = f"Found {len(matched)} entities" + (f" matching '{query}'" if query else "")

        return ToolResult(
            tool_name="search_entities",
            status="success",
            output_summary=summary,
            output={"incident_id": incident_id, "query": query, "entities": matched[:20]},
        )

    def handle_correlate_entities(self, inputs: dict[str, Any]) -> ToolResult:
        """Correlate an entity with other entities via events and graph."""
        incident_id = inputs.get("incident_id", "")
        entity_id = inputs.get("entity_id", "")

        if not incident_id or not entity_id:
            return _invalid("incident_id and entity_id are required")

        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .where(
                (TelemetryEvent.source == entity_id)
                | (TelemetryEvent.destination == entity_id)
                | (TelemetryEvent.actor == entity_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
            .limit(100)
        )
        events = list(self.session.exec(stmt).all())

        related: dict[str, dict[str, Any]] = {}
        for e in events:
            for ref in (e.source, e.destination, e.actor):
                if ref and ref != entity_id:
                    entry = related.setdefault(ref, {"count": 0, "types": set(), "attack": 0})
                    entry["count"] += 1
                    entry["types"].add(e.event_type)
                    if e.is_attack:
                        entry["attack"] += 1

        edges = self.session.exec(
            select(GraphEdge).where(
                (GraphEdge.incident_id == incident_id)
                & (
                    (GraphEdge.source_node_id == entity_id)
                    | (GraphEdge.target_node_id == entity_id)
                )
            )
        ).all()
        for edge in edges:
            other = edge.target_node_id if edge.source_node_id == entity_id else edge.source_node_id
            entry = related.setdefault(other, {"count": 0, "types": set(), "attack": 0})
            entry["count"] += 1
            entry["types"].add(edge.edge_type or "graph")

        related_list = [
            {
                "entity_id": k,
                "count": v["count"],
                "event_types": sorted(v["types"]),
                "attack_events": v["attack"],
                "score": round(min(0.95, 0.3 + 0.1 * v["count"] + 0.2 * v["attack"]), 3),
            }
            for k, v in sorted(related.items(), key=lambda x: x[1]["count"], reverse=True)
        ]

        summary = f"Correlated {entity_id} with {len(related_list)} entities"
        return ToolResult(
            tool_name="correlate_entities",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "entity_id": entity_id,
                "event_count": len(events),
                "related_entities": related_list[:10],
            },
        )

    def handle_investigate_entity(self, inputs: dict[str, Any]) -> ToolResult:
        """Deep-dive into a specific entity."""
        incident_id = inputs.get("incident_id", "")
        project_id = inputs.get("project_id", "")
        entity_id = inputs.get("entity_id", "")

        if not entity_id:
            return _invalid("entity_id is required")

        observer = WorldObserver(self.session)
        observation = observer.observe_environment(
            project_id=project_id, incident_id=incident_id, dataset_id=""
        )

        risk = 0.5
        reasons = ["entity under investigation"]

        if observation.get("incident", {}).get("found"):
            risk += observation["incident"].get("risk_score", 0.0) * 0.3
            reasons.append("incident risk")

        if observation.get("graph", {}).get("found"):
            for n in observation["graph"].get("highest_impact", []):
                if n[0] == entity_id:
                    risk += n[1] * 0.2
                    reasons.append("graph impact")

        if incident_id:
            incident = self._get_incident(incident_id)
            if incident:
                stmt = (
                    select(TelemetryEvent)
                    .where(
                        (TelemetryEvent.scenario_id == incident.scenario_id)
                        | (TelemetryEvent.incident_id == incident_id)
                    )
                    .where(
                        (TelemetryEvent.source == entity_id) | (TelemetryEvent.actor == entity_id)
                    )
                    .limit(50)
                )
                events = list(self.session.exec(stmt).all())
                {e.actor for e in events if e.actor}
                services = {e.process for e in events if e.process}
                if "scanner" in str(services).lower() or "vuln_scan" in str(services).lower():
                    risk = 0.15
                    reasons = ["identified as authorized scanner"]

        risk = round(min(0.95, risk), 3)

        summary = f"Investigated {entity_id}: risk={risk}; reasons: {', '.join(reasons)}"
        return ToolResult(
            tool_name="investigate_entity",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "project_id": project_id,
                "entity_id": entity_id,
                "risk_score": risk,
                "reasons": reasons,
                "assessment": "benign"
                if risk < 0.3
                else "suspicious"
                if risk < 0.75
                else "high_risk",
            },
        )

    def handle_trace_attack_path(self, inputs: dict[str, Any]) -> ToolResult:
        """Trace attack path from a source entity using BlastScope/graph data."""
        incident_id = inputs.get("incident_id", "")
        entity_id = inputs.get("entity_id", "")

        if not incident_id or not entity_id:
            return _invalid("incident_id and entity_id are required")

        nodes = self.session.exec(
            select(GraphNode).where(GraphNode.incident_id == incident_id)
        ).all()
        edges = self.session.exec(
            select(GraphEdge).where(GraphEdge.incident_id == incident_id)
        ).all()

        if not nodes:
            return ToolResult(
                tool_name="trace_attack_path",
                status="failure",
                error_code="graph_incomplete",
                error_message="No graph nodes for this incident; try event-level correlation.",
                output_summary="No graph nodes for this incident",
            )

        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge.source_node_id, []).append(edge.target_node_id)

        from collections import deque

        queue: deque[list[str]] = deque([[entity_id]])
        visited: set[str] = {entity_id}
        found_path: list[str] = []
        while queue:
            path = queue.popleft()
            current = path[-1]
            if any(n.node_id == current and n.is_compromised for n in nodes):
                found_path = path
                break
            for nxt in adjacency.get(current, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(path + [nxt])

        if not found_path:
            found_path = [entity_id] + adjacency.get(entity_id, [])[:3]

        summary = f"Attack path from {entity_id}: {' -> '.join(found_path)}"
        return ToolResult(
            tool_name="trace_attack_path",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "entity_id": entity_id,
                "path": found_path,
                "path_length": len(found_path),
            },
        )

    def handle_reconstruct_timeline(self, inputs: dict[str, Any]) -> ToolResult:
        """Reconstruct the event timeline for an entity or incident."""
        incident_id = inputs.get("incident_id", "")
        entity_id = inputs.get("entity_id", "")

        if not incident_id:
            return _invalid("incident_id is required")

        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
            .limit(100)
        )
        if entity_id:
            stmt = stmt.where(
                (TelemetryEvent.source == entity_id)
                | (TelemetryEvent.destination == entity_id)
                | (TelemetryEvent.actor == entity_id)
            )

        events = list(self.session.exec(stmt).all())
        timeline = [
            {
                "timestamp": e.timestamp.isoformat() if e.timestamp else "",
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source_host": e.source,
                "destination_host": e.destination,
                "user": e.actor,
                "is_attack": e.is_attack,
            }
            for e in events
        ]

        summary = f"Reconstructed timeline: {len(timeline)} events" + (
            f" for {entity_id}" if entity_id else ""
        )
        return ToolResult(
            tool_name="reconstruct_timeline",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "entity_id": entity_id,
                "event_count": len(timeline),
                "events": timeline,
            },
        )

    def handle_calculate_blast_radius(self, inputs: dict[str, Any]) -> ToolResult:
        """Calculate the blast radius for an incident."""
        incident_id = inputs.get("incident_id", "")
        if not incident_id:
            return _invalid("incident_id is required")

        engine = BlastScopeEngine(self.session)
        result = engine.run(incident_id)
        if result.get("error"):
            return ToolResult(
                tool_name="calculate_blast_radius",
                status="failure",
                error_code="blastscope_failed",
                error_message=result["error"],
            )

        total_reachable = result.get("total_reachable", 0)
        impact = result.get("impact_score", 0.0)
        summary = f"Blast radius: {total_reachable} reachable, impact={impact}"
        return ToolResult(
            tool_name="calculate_blast_radius",
            status="success",
            output_summary=summary,
            output=result,
            artifact_refs=[
                ArtifactRef(
                    ref_type="blastscope",
                    ref_id=incident_id,
                    label=f"Impact {result.get('impact_score')}",
                    link=f"/threat-ecosystem?incident_id={incident_id}",
                )
            ],
        )

    def handle_compare_baseline(self, inputs: dict[str, Any]) -> ToolResult:
        """Compare current entity activity against a simple baseline."""
        incident_id = inputs.get("incident_id", "")
        entity_id = inputs.get("entity_id", "")

        if not incident_id or not entity_id:
            return _invalid("incident_id and entity_id are required")

        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .where((TelemetryEvent.source == entity_id) | (TelemetryEvent.actor == entity_id))
            .limit(100)
        )
        events = list(self.session.exec(stmt).all())

        total = len(events)
        attack = sum(1 for e in events if e.is_attack)
        off_hours = sum(1 for e in events if getattr(e, "is_off_hours", False))
        new_device = sum(1 for e in events if getattr(e, "is_new_device", False))

        baseline = {
            "total": total,
            "attack": attack,
            "off_hours": off_hours,
            "new_device": new_device,
        }
        anomalous = any([off_hours > 0, new_device > 0, attack > total * 0.1])

        summary = (
            f"Baseline for {entity_id}: {total} events, {attack} attack, "
            f"off_hours={off_hours}, new_device={new_device}"
        )

        return ToolResult(
            tool_name="compare_baseline",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "entity_id": entity_id,
                "baseline": baseline,
                "anomalous": anomalous,
            },
        )

    def handle_rank_candidates(self, inputs: dict[str, Any]) -> ToolResult:
        """Rank suspicious candidates for an incident."""
        incident_id = inputs.get("incident_id", "")
        if not incident_id:
            return _invalid("incident_id is required")

        result = self.handle_detect_anomalies(inputs)
        result.tool_name = "rank_candidates"
        return result

    def handle_test_hypothesis(self, inputs: dict[str, Any]) -> ToolResult:
        """Test a hypothesis by correlating evidence."""
        incident_id = inputs.get("incident_id", "")
        entity_id = inputs.get("entity_id", "")
        hypothesis = inputs.get("hypothesis", "")

        if not incident_id or not entity_id:
            return _invalid("incident_id and entity_id are required")

        incident = self._get_incident(incident_id)
        if not incident:
            return _not_found("incident", incident_id)

        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .where((TelemetryEvent.source == entity_id) | (TelemetryEvent.actor == entity_id))
            .where(TelemetryEvent.is_attack == True)  # noqa: E712
            .limit(20)
        )
        attack_events = list(self.session.exec(stmt).all())

        path_result = self.handle_trace_attack_path(
            {"incident_id": incident_id, "entity_id": entity_id}
        )
        has_path = path_result.status == "success" and len(path_result.output.get("path", [])) > 1

        confidence = 0.3
        evidence_for = []
        if attack_events:
            confidence += 0.3
            evidence_for.append(f"{len(attack_events)} attack events")
        if has_path:
            confidence += 0.2
            evidence_for.append("lateral path exists")

        summary = f"Tested hypothesis '{hypothesis}': confidence={confidence:.2f}"
        return ToolResult(
            tool_name="test_hypothesis",
            status="success",
            output_summary=summary,
            output={
                "incident_id": incident_id,
                "entity_id": entity_id,
                "hypothesis": hypothesis,
                "confidence": round(min(0.95, confidence), 3),
                "evidence_for": evidence_for,
                "assessment": "supported" if confidence >= 0.6 else "weak",
            },
        )

    def handle_create_finding(self, inputs: dict[str, Any]) -> ToolResult:
        """Create a finding record for a verified conclusion."""
        incident_id = inputs.get("incident_id", "")
        statement = inputs.get("statement", "")
        confidence = float(inputs.get("confidence", 0.0))

        if not statement:
            return _invalid("statement is required")

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident_id or "global",
            actor="agent",
            action="finding_created",
            previous_state="",
            new_state="",
            reason=statement,
            control_mapping="NIST.DETECT.ANALYSIS",
            result="success",
            evidence_ref=inputs.get("evidence", ""),
        )
        last = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == (incident_id or "global"))
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        record.compute_hash(last.record_hash if last else "")
        self.session.add(record)
        self.session.commit()

        summary = f"Finding recorded: {statement} (confidence {confidence:.2f})"
        return ToolResult(
            tool_name="create_finding",
            status="success",
            output_summary=summary,
            output={
                "record_id": record.record_id,
                "statement": statement,
                "confidence": confidence,
            },
            artifact_refs=[
                ArtifactRef(
                    ref_type="finding",
                    ref_id=record.record_id,
                    label=statement[:40],
                    link=f"/ledger?incident_id={incident_id or 'global'}",
                )
            ],
        )

    def handle_verify_conclusion(self, inputs: dict[str, Any]) -> ToolResult:
        """Verify current findings/evidence for a mission."""
        from anvaya.agent.blackboard import Blackboard
        from anvaya.agent.mission import Mission
        from anvaya.models.agent_context import ExecutionContext

        execution_id = inputs.get("execution_id", "")
        if not execution_id:
            return _invalid("execution_id is required")

        context = self.session.exec(
            select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
        ).first()
        if not context:
            return _not_found("execution context", execution_id)

        mission = Mission.from_context(context.get_mission())
        blackboard = Blackboard.from_context(context.get_blackboard())

        from anvaya.agent.verification import verify_conclusion

        verification = verify_conclusion(blackboard, mission)
        return ToolResult(
            tool_name="verify_conclusion",
            status="success" if verification.passed else "failure",
            output_summary=verification.reason,
            output=verification.model_dump(),
        )


    def handle_threat_intelligence_lookup(self, inputs: dict[str, Any]) -> ToolResult:
        indicator = inputs["indicator"]
        indicator_type = inputs.get("indicator_type", "auto")

        tavily = TavilyAdapter()
        if tavily.healthy():
            result = tavily.search(indicator, indicator_type=indicator_type)
            records = result.get("records", [])
            source = result.get("source", "tavily")
            summary = f"Tavily returned {len(records)} record(s) for {indicator}"
            return ToolResult(
                tool_name="threat_intelligence_lookup",
                status="success",
                provider="tavily",
                output_summary=summary,
                output=result,
                fallback_used=source != "tavily",
                fallback_reason="" if source == "tavily" else result.get("note", ""),
            )

        fixture = {
            "indicator": indicator,
            "provider": "anvaya-local-fixture",
            "sources": "synthetic/curated",
            "records": [
                {
                    "type": "technique",
                    "value": "lateral_movement",
                    "source": "ANVAYA scenario catalog",
                    "confidence": 0.85,
                }
            ],
            "note": "Tavily unavailable. Using local threat-intel fixture.",
        }

        records = len(fixture["records"])
        summary = f"Local fixture returned {records} record(s) for {indicator}"

        return ToolResult(
            tool_name="threat_intelligence_lookup",
            status="success",
            provider="anvaya-local-fixture",
            output_summary=summary,
            output=fixture,
            fallback_used=True,
            fallback_reason="Tavily not configured or unavailable",
        )

    def handle_trigger_automation(self, inputs: dict[str, Any]) -> ToolResult:
        workflow = inputs["workflow"]
        incident_id = inputs["incident_id"]
        payload = inputs.get("payload", {})

        n8n = N8NAdapter()
        if n8n.healthy():
            result = n8n.trigger(workflow, payload={"incident_id": incident_id, **payload})
            if not result.get("fallback_used"):
                return ToolResult(
                    tool_name="trigger_automation",
                    status="success",
                    provider="n8n",
                    output_summary=f"n8n workflow '{workflow}' triggered for {incident_id}",
                    output=result,
                    fallback_used=False,
                )
            fallback_reason = result.get("fallback_reason", "n8n request failed")
        else:
            fallback_reason = "n8n not configured or unavailable"

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            actor="agent",
            action=f"automation_{workflow}",
            previous_state="",
            new_state="",
            reason=f"{fallback_reason}. Local handler recorded automation '{workflow}'.",
            control_mapping="NIST.RESPOND.AUTOMATION",
            result="success",
        )
        self.session.add(record)
        self.session.commit()

        return ToolResult(
            tool_name="trigger_automation",
            status="success",
            provider="anvaya-local-handler",
            output_summary=f"Automation '{workflow}' recorded locally for {incident_id}",
            output={"workflow": workflow, "incident_id": incident_id, "status": "recorded"},
            fallback_used=True,
            fallback_reason=fallback_reason,
        )

    def handle_notify_via_email(self, inputs: dict[str, Any]) -> ToolResult:
        """Send a Gmail notification or record a local fallback."""
        to = inputs["to"]
        subject = inputs["subject"]
        body = inputs["body"]

        gmail = GmailAdapter()
        if gmail.healthy():
            result = gmail.send(to, subject, body)
            if not result.get("fallback_used"):
                return ToolResult(
                    tool_name="notify_via_email",
                    status="success",
                    provider="gmail",
                    output_summary=f"Email sent to {to}",
                    output=result,
                    fallback_used=False,
                )
            fallback_reason = result.get("fallback_reason", "Gmail send failed")
        else:
            fallback_reason = "Gmail not configured or unavailable"

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=inputs.get("incident_id", ""),
            actor="agent",
            action="notify_via_email",
            previous_state="",
            new_state="",
            reason=f"{fallback_reason}. Intended: to={to}, subject={subject}",
            control_mapping="NIST.RESPOND.NOTIFY",
            result="success",
        )
        self.session.add(record)
        self.session.commit()

        return ToolResult(
            tool_name="notify_via_email",
            status="success",
            provider="anvaya-local-handler",
            output_summary=f"Email to {to} recorded locally",
            output={
                "to": to,
                "subject": subject,
                "status": "recorded",
                "fallback_reason": fallback_reason,
            },
            fallback_used=True,
            fallback_reason=fallback_reason,
        )

    def handle_lyzr_propose_rule(self, inputs: dict[str, Any]) -> ToolResult:
        """Use Lyzr as an alternate reasoning provider for rule proposal."""
        from anvaya.agent.adapters import LyzrAdapter

        incident_id = inputs["incident_id"]
        attack_family = inputs["attack_family"]

        lyzr = LyzrAdapter()
        if lyzr.healthy():
            prompt = (
                "Analyze the following security telemetry evidence and "
                "propose a detection rule.\n"
                "\n"
                f"Incident: {incident_id}\n"
                f"Attack family: {attack_family}\n"
                "\n"
                "Propose a concise rule name and description for detecting "
                "this attack pattern.\n"
                "Respond in JSON format with keys: name, description"
            )
            result = lyzr.propose(prompt)
            if not result.get("fallback_used"):
                content = result.get("content", {})
                return ToolResult(
                    tool_name="lyzr_propose_rule",
                    status="success",
                    provider="lyzr",
                    output_summary=f"Lyzr proposed rule for {attack_family}",
                    output=content,
                    fallback_used=False,
                )
            fallback_reason = result.get("fallback_reason", "Lyzr request failed")
        else:
            fallback_reason = "Lyzr not configured or unavailable"

        fallback = {
            "name": f"Backtrack-Rule-{attack_family}",
            "description": (
                "Deterministically proposed rule from evidence analysis "
                f"for {attack_family}"
            ),
        }
        return ToolResult(
            tool_name="lyzr_propose_rule",
            status="success",
            provider="anvaya-local-fixture",
            output_summary=f"Local fallback rule for {attack_family}",
            output=fallback,
            fallback_used=True,
            fallback_reason=fallback_reason,
        )


    def handle_spawn_subagent(self, inputs: dict[str, Any]) -> ToolResult:
        """Spawn a Devin-like subagent from inside an execution."""
        from anvaya.agent.subagents import subagent_spawner

        task = inputs.get("task", "")
        if not task:
            return ToolResult(
                tool_name="spawn_subagent",
                status="failure",
                error_code="missing_task",
                error_message="subagent task is required",
                output_summary="subagent task is required",
            )

        profile_id = inputs.get("profile_id", "general")
        mode = inputs.get("mode", "background")
        parent_execution_id = inputs.get("parent_execution_id") or self._current_execution_id
        incident_id = inputs.get("incident_id", "")

        if not parent_execution_id:
            return ToolResult(
                tool_name="spawn_subagent",
                status="failure",
                error_code="missing_parent",
                error_message="parent_execution_id is required",
                output_summary="parent_execution_id is required",
            )

        try:
            sub = subagent_spawner.spawn(
                self.session,
                task=task,
                profile_id=profile_id,
                parent_execution_id=parent_execution_id,
                incident_id=incident_id,
                mode=mode,
            )
            status = "success" if sub.status != "failed" else "failure"
            summary = f"Subagent {sub.subagent_id} ({mode}) for {profile_id}: {sub.status}"
            return ToolResult(
                tool_name="spawn_subagent",
                status=status,
                output_summary=summary,
                output={
                    "subagent_id": sub.subagent_id,
                    "profile_id": sub.profile_id,
                    "mode": sub.mode,
                    "status": sub.status,
                    "child_execution_id": sub.child_execution_id,
                },
                artifact_refs=[
                    ArtifactRef(
                        ref_type="subagent",
                        ref_id=sub.subagent_id,
                        label=sub.title,
                        link=f"/agent/subagents/{sub.subagent_id}",
                    )
                ],
            )
        except Exception as exc:
            return ToolResult(
                tool_name="spawn_subagent",
                status="failure",
                error_code="spawn_failed",
                error_message=str(exc),
                output_summary=str(exc),
            )

    def handle_run_tests(self, inputs: dict[str, Any]) -> ToolResult:
        """Run a pytest test path and report results."""
        test_path = inputs.get("test_path", "tests")

        base = Path(settings.base_dir).resolve()
        requested = (base / test_path).resolve()
        if not str(requested).startswith(str(base / "tests")):
            return ToolResult(
                tool_name="run_tests",
                status="failure",
                error_code="invalid_test_path",
                error_message="test_path must be under tests/",
                output_summary="test_path must be under tests/",
            )

        rel = requested.relative_to(base)
        cmd = [sys.executable, "-m", "pytest", str(rel), "-q", "--tb=short"]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(base),
            )
            passed = proc.returncode == 0
            lines = [line for line in proc.stdout.strip().splitlines() if line]
            summary = lines[-1] if lines else "No output"
            return ToolResult(
                tool_name="run_tests",
                status="success" if passed else "failure",
                output_summary=summary,
                output={
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "test_path": str(rel),
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="run_tests",
                status="failure",
                error_code="timeout",
                error_message="Test run timed out",
                output_summary="Test run timed out",
            )
        except Exception as exc:
            return ToolResult(
                tool_name="run_tests",
                status="failure",
                error_code="test_error",
                error_message=str(exc),
                output_summary=str(exc),
            )


    def _get_incident(self, incident_id: str) -> Incident | None:
        return self.session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()

    def _audit(
        self,
        incident: Incident,
        action: str,
        prev_state: str,
        new_state: str,
        rule_version: str = "",
        replay_id: str = "",
        evidence_ref: str = "",
    ) -> None:
        last = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident.incident_id)
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        prev_hash = last.record_hash if last else ""

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            actor="agent",
            action=action,
            previous_state=prev_state,
            new_state=new_state,
            reason=f"Agent: {action}",
            rule_version=rule_version,
            replay_id=replay_id,
            evidence_ref=evidence_ref,
            control_mapping=f"NIST.DETECT.{action.upper()}",
            result="success",
        )
        record.compute_hash(prev_hash)
        self.session.add(record)


def _safe_summary(inputs: dict[str, Any]) -> str:
    """Produce a short, safe input summary without secrets."""
    if not inputs:
        return ""
    parts = []
    for k, v in inputs.items():
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
        elif isinstance(v, dict):
            parts.append(f"{k}={{{','.join(v.keys())}}}")
    return "; ".join(parts[:6])


def _not_found(entity: str, ref: str) -> ToolResult:
    return ToolResult(
        tool_name="",
        status="failure",
        error_code="not_found",
        error_message=f"{entity} not found: {ref}",
        output_summary=f"{entity} not found: {ref}",
    )


def _invalid(message: str) -> ToolResult:
    return ToolResult(
        tool_name="",
        status="failure",
        error_code="invalid_input",
        error_message=message,
        output_summary=message,
    )
