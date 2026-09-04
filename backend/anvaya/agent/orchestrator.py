"""Agent orchestrator — policy-driven tool selection for ANVAYA."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from anvaya.agent.agent_loop import AgentLoop, _build_artifact_steps
from anvaya.agent.artifact_utils import infer_artifact_action, infer_artifact_types
from anvaya.agent.decision import DecisionEngine
from anvaya.agent.events import EventStore, event_store
from anvaya.agent.executor import LocalToolExecutor

from anvaya.agent.memory import MemoryStore
from anvaya.agent.messaging import MessageGenerator
from anvaya.agent.profiles import AgentProfile, get_profile, get_profile_for_objective
from anvaya.agent.registry import default_tool_registry
from anvaya.agent.schemas import ToolResult
from anvaya.agent.world import WorldObserver
from anvaya.logging import get_logger
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.incident import Incident

logger = get_logger("anvaya.agent.orchestrator")


class AgentOrchestrator:
    """Deterministic policy orchestrator with profile-driven messaging.

    The orchestrator:
    - selects a profile from the objective or an explicit profile_id,
    - emits short operational messages before/after each tool,
    - chooses tools based on incident state and available artifacts,
    - marks fallback use truthfully.

    No external model is required. If an OpenAI/Lyzr adapter is configured and
    healthy, a future version can delegate planning; the local policy always
    runs as the final fallback.
    """

    def __init__(
        self,
        session: Session,
        store: EventStore | None = None,
        profile_id: str = "",
        model_id: str = "",
    ):
        self.session = session
        self.store = store or event_store
        self.registry = default_tool_registry()
        self.executor = LocalToolExecutor(session)
        self.profile_id = profile_id
        self.model_id = model_id

    def start(
        self,
        objective: str,
        incident_id: str = "",
        project_id: str = "",
        provider: str = "anvaya",
    ) -> str:
        """Create a new execution and live context, returning the execution ID."""
        execution_id = self.store.create_execution(self.session, objective, incident_id, provider)

        context = ExecutionContext(
            execution_id=execution_id,
            objective=objective,
            incident_id=incident_id,
            project_id=project_id,
            status="running",
            plan=[],
            observations=[],
            messages=[],
            reasoning_summary="",
            current_action={},
            model="",
            provider=provider,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(context)
        self.session.commit()

        return execution_id

    def run(
        self,
        execution_id: str,
        objective: str = "",
        incident_id: str = "",
        project_id: str = "",
        plan: list[dict[str, Any]] | None = None,
        profile: AgentProfile | None = None,
        adaptive: bool | None = None,
    ) -> Execution:
        """Run the live, reasoning-aware orchestration loop for an execution.

        If ``adaptive`` is not explicitly set, a provided concrete ``plan``
        disables adaptive mode so the plan is executed as given (used by
        subagents); otherwise the loop is adaptive.
        """
        execution = self.store.get_execution(self.session, execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if objective:
            execution.objective = objective
        execution.status = "running"
        execution.mode = "agentic"
        execution.completed_at = None
        execution.duration_ms = 0.0
        self.session.add(execution)
        self.session.commit()

        incident_id = incident_id or execution.incident_id or _extract_incident_id(objective)
        project_id = project_id or _extract_project_id(objective) or ""
        if not incident_id and not project_id:
            project_id = _resolve_implicit_project(self.session, objective)
            if not project_id:
                _fail(
                    self,
                    execution_id,
                    "missing_incident",
                    "Could not determine incident_id from objective.",
                )
                return execution

        requested_artifacts = infer_artifact_types(objective) if objective else []
        if (
            incident_id
            and not _is_project_id(incident_id)
            and _get_incident(self.session, incident_id)
            and requested_artifacts
        ):
            mixed_project_id = (
                project_id
                or _extract_project_id(objective)
                or _resolve_implicit_project(self.session, objective)
                or _get_latest_project_id(self.session)
            )
            if mixed_project_id:
                return self._run_mixed_plan(
                    execution,
                    objective,
                    incident_id,
                    mixed_project_id,
                    profile,
                    requested_artifacts,
                )

        is_project = _is_project_id(incident_id) or _is_project_id(project_id)
        project_id = project_id or (incident_id if is_project else "")
        if project_id and not _get_incident(self.session, incident_id):
            execution.incident_id = ""
            self.session.add(execution)
            self.session.commit()
            return self._run_project_plan(execution, objective, project_id, profile)

        execution.incident_id = incident_id
        self.session.add(execution)
        self.session.commit()

        if profile is None:
            profile_id = self.profile_id or _extract_profile_hint(objective) or ""
            profile = get_profile(profile_id) or get_profile_for_objective(objective)
        messenger = MessageGenerator(profile)

        active_model = None
        initial_plan = plan
        if initial_plan is None:
            from anvaya.agent.planner import resolve_planner

            context = _build_context(self.session, incident_id, objective or execution.objective)
            planner, active_model = resolve_planner(profile, model_id=self.model_id)

            if active_model:
                execution.provider = active_model.provider
                self.session.add(execution)
                self.session.commit()

                from sqlmodel import select

                live_context = self.session.exec(
                    select(ExecutionContext).where(
                        ExecutionContext.execution_id == execution.execution_id
                    )
                ).first()
                if live_context:
                    live_context.model = active_model.id
                    live_context.provider = active_model.provider
                    self.session.add(live_context)
                    self.session.commit()

            initial_plan = planner.build_plan(
                self.session, incident_id, context=context, profile=profile
            )
            if initial_plan is None:
                initial_plan = _build_plan(self.session, incident_id, profile)

        is_adaptive = plan is None if adaptive is None else adaptive
        loop = AgentLoop(self)
        if is_adaptive:
            world = WorldObserver(self.session)
            decision = DecisionEngine(world)
            memory = MemoryStore(self.session)
            return loop.run_adaptive(
                execution,
                incident_id,
                profile,
                active_model,
                messenger,
                objective,
                project_id=project_id,
                world=world,
                decision=decision,
                memory=memory,
                initial_plan=initial_plan or [],
            )

        return loop.run_investigation(
            execution, incident_id, initial_plan or [], profile, active_model, messenger, objective
        )

    def _run_project_plan(
        self,
        execution: Execution,
        objective: str,
        project_id: str,
        profile: AgentProfile | None,
    ) -> Execution:
        """Run a project-scoped artifact-generation plan."""
        from sqlmodel import select

        from anvaya.models.project import Project

        project = self.session.exec(select(Project).where(Project.project_id == project_id)).first()
        if not project:
            _fail(
                self,
                execution.execution_id,
                "project_not_found",
                f"Project {project_id} not found",
            )
            return self.store.get_execution(self.session, execution.execution_id) or execution

        action = infer_artifact_action(objective)
        requested = infer_artifact_types(objective)
        if not requested:
            requested = ["all"]

        from anvaya.agent.planner import resolve_planner
        from anvaya.agent.profiles import get_model, get_profile_for_objective

        profile = profile or get_profile_for_objective(objective)

        active_model = None
        if self.model_id:
            active_model = get_model(self.model_id)
        if active_model is None:
            _, active_model = resolve_planner(profile, model_id=self.model_id)
        if active_model:
            execution.provider = active_model.provider
            self.session.add(execution)
            self.session.commit()

            live_context = self.session.exec(
                select(ExecutionContext).where(
                    ExecutionContext.execution_id == execution.execution_id
                )
            ).first()
            if live_context:
                live_context.model = active_model.id
                live_context.provider = active_model.provider
                self.session.add(live_context)
                self.session.commit()

        loop = AgentLoop(self)
        return loop.run_project_plan(
            execution, project_id, objective, profile, action, requested, active_model
        )

    def _run_mixed_plan(
        self,
        execution: Execution,
        objective: str,
        incident_id: str,
        project_id: str,
        profile: AgentProfile | None,
        requested_artifacts: list[str],
    ) -> Execution:
        """Run a mixed investigation + artifact-generation plan."""
        from anvaya.agent.planner import resolve_planner
        from anvaya.agent.profiles import get_model, get_profile_for_objective
        from anvaya.models.project import Project

        project = self.session.exec(
            select(Project).where(Project.project_id == project_id)
        ).first()
        if not project:
            _fail(
                self,
                execution.execution_id,
                "project_not_found",
                f"Project {project_id} not found",
            )
            return self.store.get_execution(self.session, execution.execution_id) or execution

        action = infer_artifact_action(objective)

        profile = profile or get_profile_for_objective(objective)

        active_model = None
        if self.model_id:
            active_model = get_model(self.model_id)
        if active_model is None:
            _, active_model = resolve_planner(profile, model_id=self.model_id)
        if active_model:
            execution.provider = active_model.provider
            self.session.add(execution)
            self.session.commit()

            live_context = self.session.exec(
                select(ExecutionContext).where(
                    ExecutionContext.execution_id == execution.execution_id
                )
            ).first()
            if live_context:
                live_context.model = active_model.id
                live_context.provider = active_model.provider
                self.session.add(live_context)
                self.session.commit()

        investigation_plan = _build_plan(self.session, incident_id, profile)
        artifact_plan = _build_artifact_steps(action, requested_artifacts, project_id)
        combined_plan = investigation_plan + artifact_plan

        execution.incident_id = incident_id
        self.session.add(execution)
        self.session.commit()

        messenger = MessageGenerator(profile)
        loop = AgentLoop(self)
        return loop.run_investigation(
            execution,
            incident_id,
            combined_plan,
            profile,
            active_model,
            messenger,
            objective,
            project_id=project_id,
        )

    def _emit_tool_failed(
        self,
        execution_id: str,
        sequence: int,
        tool_name: str,
        inputs: dict[str, Any],
        error_code: str,
        error_message: str,
    ) -> int:
        """Emit a tool.failed event and return the next sequence number."""
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "tool.failed",
            tool_name=tool_name,
            status="failed",
            label=f"{tool_name} failed",
            error_code=error_code,
            error_message=error_message,
            payload={"inputs": _safe_payload(inputs)},
        )
        return sequence + 1


def _extract_incident_id(objective: str) -> str:
    """Try to extract an incident ID from the objective string."""
    patterns = [
        r"(INC-[A-Z0-9]+)",
        r"(incident[-\s]?id?:?\s*)([A-Z0-9-]+)",
        r"(INC[\s-]+[A-Z0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, objective, re.IGNORECASE)
        if match:
            if match.lastindex and match.lastindex > 1:
                return match.group(2).strip().upper()
            return match.group(1).strip().upper()
    return ""


def _extract_profile_hint(objective: str) -> str:
    """Try to extract a profile hint from the objective string."""
    obj = objective.lower()
    if any(k in obj for k in ("path", "reach", "orbit", "segment")):
        return "pathfinder"
    if any(k in obj for k in ("respond", "contain", "block", "isolate")):
        return "responder"
    if any(k in obj for k in ("audit", "verify evidence")):
        return "auditor"
    return ""


def _build_plan(
    session: Session,
    incident_id: str,
    profile=None,
) -> list[dict[str, Any]]:
    """Build the investigation plan for a missed-attack scenario.

    The plan is the full judge proof: context → ground-truth → evidence → rule
    → validate → replay → catch → blast → whatif → audit → seal.
    Profiles can influence ordering/selection via preferred tools.
    """
    from sqlmodel import select

    incident = session.exec(select(Incident).where(Incident.incident_id == incident_id)).first()
    if not incident:
        return []

    base: list[dict[str, Any]] = [
        {
            "tool": "get_incident",
            "inputs": {"incident_id": incident_id},
            "label": "Loading incident",
            "progress": "Loading incident details",
            "completed": "Incident loaded",
        },
        {
            "tool": "get_telemetry",
            "inputs": {"incident_id": incident_id, "limit": 100},
            "label": "Inspecting telemetry",
            "progress": "Loading telemetry events",
            "completed": "Telemetry inspected",
        },
        {
            "tool": "inspect_detection",
            "inputs": {"incident_id": incident_id},
            "label": "Inspecting detection",
            "progress": "Checking detection runs",
            "completed": "Detection inspected",
            "optional": True,
        },
        {
            "tool": "confirm_ground_truth",
            "inputs": {"incident_id": incident_id},
            "label": "Confirming ground truth",
            "progress": "Confirming attack ground truth",
            "completed": "Ground truth confirmed",
        },
        {
            "tool": "run_sentinel_trace",
            "inputs": {"incident_id": incident_id},
            "label": "Backtracking evidence",
            "progress": "Walking back through evidence",
            "completed": "Evidence backtracked",
        },
        {
            "tool": "propose_rule",
            "inputs": {"incident_id": incident_id},
            "label": "Proposing detection rule",
            "progress": "Building candidate rule from evidence",
            "completed": "Rule proposed",
        },
        {
            "tool": "validate_rule",
            "inputs": {"incident_id": incident_id},
            "label": "Validating rule",
            "progress": "Validating rule against telemetry",
            "completed": "Rule validated",
        },
        {
            "tool": "run_replay",
            "inputs": {"incident_id": incident_id},
            "label": "Replaying attack",
            "progress": "Running identical replay with patched rule",
            "completed": "Replay completed",
        },
        {
            "tool": "run_blastscope",
            "inputs": {"incident_id": incident_id},
            "label": "Running BlastScope",
            "progress": "Computing blast radius",
            "completed": "BlastScope complete",
        },
        {
            "tool": "build_or_update_ecosystem",
            "inputs": {"incident_id": incident_id, "mode": "CONTAIN"},
            "label": "Updating ecosystem",
            "progress": "Building ecosystem model",
            "completed": "Ecosystem updated",
            "optional": True,
        },
        {
            "tool": "run_orbit_analysis",
            "inputs": {"incident_id": incident_id},
            "label": "Running orbit analysis",
            "progress": "Computing orbit/risk view",
            "completed": "Orbit analysis complete",
            "optional": True,
        },
        {
            "tool": "run_what_if",
            "inputs": {
                "incident_id": incident_id,
                "changes": {"is_off_hours": 0.0, "is_new_device": 0.0},
            },
            "label": "Running What-If",
            "progress": "Computing counterfactual risk",
            "completed": "What-If complete",
        },
        {
            "tool": "append_audit_record",
            "inputs": {
                "incident_id": incident_id,
                "action": "agent_investigation_complete",
                "previous_state": incident.status.value,
                "new_state": "sealed",
                "reason": "Agent completed self-correction investigation",
                "control_mapping": "NIST.RESPOND.AUDIT",
            },
            "label": "Appending audit record",
            "progress": "Appending audit record",
            "completed": "Audit record appended",
        },
        {
            "tool": "verify_audit_chain",
            "inputs": {"incident_id": incident_id},
            "label": "Verifying audit chain",
            "progress": "Verifying audit hash chain",
            "completed": "Audit chain verified",
        },
        {
            "tool": "seal_incident",
            "inputs": {"incident_id": incident_id},
            "label": "Sealing incident",
            "progress": "Sealing incident",
            "completed": "Incident sealed",
            "stop_on_failure": True,
        },
    ]

    if profile and profile.id == "pathfinder":
        if not any(s["tool"] == "run_reachability" for s in base):
            base.insert(
                10,
                {
                    "tool": "run_reachability",
                    "inputs": {"incident_id": incident_id},
                    "label": "Running reachability",
                    "progress": "Computing reachability",
                    "completed": "Reachability complete",
                    "optional": True,
                },
            )
        if not any(s["tool"] == "run_segment_analysis" for s in base):
            base.insert(
                11,
                {
                    "tool": "run_segment_analysis",
                    "inputs": {"incident_id": incident_id},
                    "label": "Running segment analysis",
                    "progress": "Ranking segments",
                    "completed": "Segment analysis complete",
                    "optional": True,
                },
            )

    return base


def _result_summary(results: list[ToolResult]) -> str:
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    failed = total - success
    artifacts = sum(len(r.artifact_refs) for r in results)
    fallback = any(r.fallback_used for r in results)
    parts = [f"Ran {total} tools: {success} succeeded, {failed} failed, {artifacts} artifacts."]
    if fallback:
        parts.append("External fallback used.")
    return " ".join(parts)


def _summary_items(results: list[ToolResult]) -> list[dict[str, Any]]:
    return [{"tool": r.tool_name, "status": r.status, "summary": r.output_summary} for r in results]


def _safe_payload(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return a safe copy of tool inputs."""
    safe: dict[str, Any] = {}
    for k, v in inputs.items():
        if isinstance(v, (str, int, float, bool)):
            safe[k] = v
        elif isinstance(v, dict):
            safe[k] = {sk: sv for sk, sv in v.items() if isinstance(sv, (str, int, float, bool))}
        else:
            safe[k] = str(v)[:120]
    return safe


def _fail(
    orchestrator: AgentOrchestrator,
    execution_id: str,
    error_code: str,
    error_message: str,
    fallback_used: bool = False,
    fallback_reason: str = "",
) -> None:
    """Mark an execution as failed and emit the final event."""
    orchestrator.store.emit(
        orchestrator.session,
        execution_id,
        _next_sequence(orchestrator, execution_id),
        "agent.failed",
        label="Investigation failed",
        error_code=error_code,
        error_message=error_message,
        payload={"fallback_used": fallback_used, "fallback_reason": fallback_reason},
    )
    orchestrator.store.complete_execution(
        orchestrator.session,
        execution_id,
        "failed",
        result_summary=f"Investigation failed: {error_message}",
        error_code=error_code,
        error_message=error_message,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


def _next_sequence(orchestrator: AgentOrchestrator, execution_id: str) -> int:
    """Return the next sequence number for an execution."""
    from sqlmodel import select

    stmt = (
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.sequence.desc())
    )
    last = orchestrator.session.exec(stmt).first()
    return (last.sequence + 1) if last else 1


def _build_context(session: Session, incident_id: str, objective: str) -> dict[str, Any]:
    """Gather a small, relevant context snapshot for the planner.

    Do not dump the whole database. Include only what the model needs to select
    the right tool.
    """
    from sqlmodel import select

    from anvaya.models.detection import DetectionRun
    from anvaya.models.incident import Incident
    from anvaya.models.telemetry import TelemetryEvent

    context: dict[str, Any] = {
        "objective": objective,
        "incident_id": incident_id,
    }

    incident = session.exec(select(Incident).where(Incident.incident_id == incident_id)).first()
    if incident:
        context.update(
            {
                "title": incident.title,
                "severity": incident.severity,
                "status": incident.status.value,
                "self_correction_status": incident.self_correction_status.value,
                "attack_family": incident.attack_family,
            }
        )

        telemetry_count = session.exec(
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
        ).all()
        context["telemetry_count"] = len(telemetry_count)

    detection = session.exec(
        select(DetectionRun)
        .where(DetectionRun.incident_id == incident_id)
        .order_by(DetectionRun.started_at.desc())
    ).first()
    if detection:
        context["detection_caught"] = detection.detected
    else:
        context["detection_caught"] = False

    return context


def _extract_project_id(objective: str) -> str:
    """Try to extract a project ID from the objective string."""
    patterns = [
        r"(PRJ-[A-Z0-9-]+)",
        r"project[-\s]?id?:?\s*([A-Z0-9-]+)",
        r"project\s+([A-Z0-9-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, objective, re.IGNORECASE)
        if match:
            if match.lastindex and match.lastindex > 1:
                return match.group(2).strip().upper()
            return match.group(1).strip().upper()
    return ""


def _is_project_id(value: str) -> bool:
    """Check whether a value looks like a project identifier."""
    return bool(value and value.upper().startswith("PRJ-"))


def _resolve_implicit_project(session: Session, objective: str) -> str:
    """Attempt to find a project when the objective implies artifact management.

    Uses the same artifact type/action inference as the agent loop so that
    every supported artifact type (orbits, reach, arbor, trophy wall, etc.)
    can be targeted without an explicit project ID. Returns "" if the
    objective does not look like an artifact command.
    """
    if not objective:
        return ""

    action = infer_artifact_action(objective)
    requested = infer_artifact_types(objective)
    if not requested:
        return ""

    has_action_keyword = re.search(
        r"\b(generate|generating|build|create|run|refresh|make|regenerate|regen|"
        r"re-generate|delete|remove|clear|wipe|update|produce)\b",
        objective,
        re.IGNORECASE,
    )
    if action == "generate" and not has_action_keyword:
        return ""

    from sqlmodel import select

    from anvaya.models.project import Project

    latest = session.exec(select(Project).order_by(Project.updated_at.desc()).limit(1)).first()
    if latest:
        return latest.project_id
    return ""


def _get_latest_project_id(session: Session) -> str:
    """Return the most recently updated project ID, or ''."""
    from anvaya.models.project import Project

    latest = session.exec(select(Project).order_by(Project.updated_at.desc()).limit(1)).first()
    return latest.project_id if latest else ""


def _get_incident(session: Session, incident_id: str) -> Incident | None:
    """Load an incident by ID, or None if it is not a real incident."""
    if _is_project_id(incident_id):
        return None
    from sqlmodel import select

    from anvaya.models.incident import Incident

    return session.exec(select(Incident).where(Incident.incident_id == incident_id)).first()
