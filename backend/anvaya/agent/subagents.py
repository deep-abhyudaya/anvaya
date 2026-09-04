"""Devin-like subagent spawner for ANVAYA.

Subagents are child agent executions spawned by a parent execution. They can run
in the foreground (blocking) or background (parallel) and are constrained by a
profile that controls which tools they may use and how deeply they can nest.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from threading import Lock, Thread
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlmodel import Session, select

from anvaya.agent.events import EventStore, event_store
from anvaya.agent.orchestrator import AgentOrchestrator
from anvaya.agent.profiles import AgentProfile, get_profile
from anvaya.agent.registry import default_tool_registry
from anvaya.agent.schemas import ExecutionEventPayload
from anvaya.logging import get_logger
from anvaya.models.execution import ExecutionEvent
from anvaya.models.subagent import SubagentExecution

logger = get_logger("anvaya.agent.subagents")


class SubagentProfile(BaseModel):
    """Profile that defines what a subagent can do."""

    id: str
    name: str
    display_name: str
    description: str
    icon: str = "bot"
    accent: str = "cyan"
    model: str = "anvaya-local-orchestrator"
    allowed_tools: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    fallback_tools: list[str] = Field(default_factory=list)
    confirmation_policy: str = "read-only"
    max_nesting: int = 0
    status: str = "active"

    def to_agent_profile(self) -> AgentProfile:
        """Return an AgentProfile that can drive the orchestrator."""
        base = get_profile("sentinel")
        if base is None:
            raise RuntimeError("Sentinel profile not found; cannot build subagent profile")
        preferred = self.preferred_tools or self.allowed_tools
        return base.model_copy(
            update={
                "id": self.id,
                "name": self.name,
                "display_name": self.display_name,
                "purpose": self.description,
                "preferred_tools": preferred,
                "fallback_tools": self.fallback_tools,
                "confirmation_policy": self.confirmation_policy,
                "icon": self.icon,
                "accent": self.accent,
                "model_name": self.model,
            }
        )


def _explore_tools() -> list[str]:
    return [
        "get_incident",
        "get_telemetry",
        "inspect_detection",
        "get_metrics",
        "verify_audit_chain",
        "threat_intelligence_lookup",
    ]


def _tester_tools() -> list[str]:
    return [
        "get_incident",
        "get_telemetry",
        "inspect_detection",
        "confirm_ground_truth",
        "propose_rule",
        "validate_rule",
        "run_replay",
        "run_blastscope",
        "run_what_if",
        "verify_audit_chain",
        "run_tests",
    ]


def default_subagent_profiles() -> list[SubagentProfile]:
    """Return built-in subagent profiles."""
    explore = _explore_tools()
    tester = _tester_tools()
    all_tools = [t.name for t in default_tool_registry().list_tools()]
    return [
        SubagentProfile(
            id="explore",
            name="Explore",
            display_name="Explore — Research",
            description=(
                "Read-only research subagent for exploration, evidence review, and research."
            ),
            icon="search",
            accent="green",
            model="anvaya-local-orchestrator",
            allowed_tools=explore,
            preferred_tools=explore,
            fallback_tools=["threat_intelligence_lookup"],
            confirmation_policy="read-only",
            max_nesting=0,
        ),
        SubagentProfile(
            id="general",
            name="General",
            display_name="General — Builder",
            description="General-purpose subagent that can run the full ANVAYA tool chain.",
            icon="bot",
            accent="cyan",
            model="anvaya-local-orchestrator",
            allowed_tools=all_tools,
            preferred_tools=all_tools,
            fallback_tools=[],
            confirmation_policy="mutating",
            max_nesting=0,
        ),
        SubagentProfile(
            id="tester",
            name="Tester",
            display_name="Tester — Runner",
            description=(
                "Test runner subagent that validates rules, replays attacks, and runs tests."
            ),
            icon="check-circle",
            accent="amber",
            model="anvaya-local-orchestrator",
            allowed_tools=tester,
            preferred_tools=tester,
            fallback_tools=["run_tests"],
            confirmation_policy="mutating",
            max_nesting=0,
        ),
    ]


def get_subagent_profile(profile_id: str) -> SubagentProfile | None:
    """Get a subagent profile by ID."""
    for p in default_subagent_profiles():
        if p.id == profile_id:
            return p
    return None


def _extract_test_path(task: str) -> str:
    """Try to pull an explicit test path out of the task text."""
    match = re.search(r"tests/[\w/\-_.]+\.py", task)
    if match:
        return match.group(0)
    if re.search(r"\btest_\w+\b", task):
        if (match := re.search(r"\btest_\w+\b", task)):
            return f"tests/{match.group(0)}.py"
        return "tests"
    return "tests"


def build_subagent_plan(
    session: Session,
    task: str,
    incident_id: str,
    allowed_tools: list[str],
    max_steps: int = 14,
) -> list[dict[str, Any]]:
    """Build a deterministic plan for a subagent from the task and allowed tools."""
    from anvaya.agent.orchestrator import _build_plan

    plan: list[dict[str, Any]] = []
    task_lower = task.lower()

    if incident_id and "get_incident" in allowed_tools:
        plan.append(
            {
                "tool": "get_incident",
                "inputs": {"incident_id": incident_id},
                "label": "Loading incident",
                "progress": "Loading incident details",
                "completed": "Incident loaded",
            }
        )

    if incident_id:
        base = _build_plan(session, incident_id, profile=None)
        seen = {step["tool"] for step in plan}
        for step in base:
            if step["tool"] in allowed_tools and step["tool"] not in seen:
                plan.append(step)

    if ("test" in task_lower or "pytest" in task_lower) and "run_tests" in allowed_tools:
        if not any(s["tool"] == "run_tests" for s in plan):
            plan.append(
                {
                    "tool": "run_tests",
                    "inputs": {"test_path": _extract_test_path(task)},
                    "label": "Running tests",
                    "progress": "Running test suite",
                    "completed": "Tests complete",
                    "optional": True,
                }
            )

    if ("blast" in task_lower or "impact" in task_lower) and "run_blastscope" in allowed_tools:
        if not any(s["tool"] == "run_blastscope" for s in plan):
            plan.append(
                {
                    "tool": "run_blastscope",
                    "inputs": {"incident_id": incident_id},
                    "label": "Running BlastScope",
                    "progress": "Computing blast radius",
                    "completed": "BlastScope complete",
                }
            )

    if (
        "what if" in task_lower or "counterfactual" in task_lower
    ) and "run_what_if" in allowed_tools:
        if not any(s["tool"] == "run_what_if" for s in plan):
            plan.append(
                {
                    "tool": "run_what_if",
                    "inputs": {
                        "incident_id": incident_id,
                        "changes": {"is_off_hours": 0.0, "is_new_device": 0.0},
                    },
                    "label": "Running What-If",
                    "progress": "Computing counterfactual risk",
                    "completed": "What-If complete",
                }
            )

    if ("audit" in task_lower or "chain" in task_lower) and "verify_audit_chain" in allowed_tools:
        if not any(s["tool"] == "verify_audit_chain" for s in plan):
            plan.append(
                {
                    "tool": "verify_audit_chain",
                    "inputs": {"incident_id": incident_id} if incident_id else {},
                    "label": "Verifying audit chain",
                    "progress": "Verifying audit hash chain",
                    "completed": "Audit chain verified",
                    "optional": True,
                }
            )

    if (
        "threat" in task_lower or "intel" in task_lower
    ) and "threat_intelligence_lookup" in allowed_tools:
        if not any(s["tool"] == "threat_intelligence_lookup" for s in plan):
            plan.append(
                {
                    "tool": "threat_intelligence_lookup",
                    "inputs": {
                        "indicator": incident_id or "lateral_movement",
                        "indicator_type": "auto",
                    },
                    "label": "Looking up threat intelligence",
                    "progress": "Querying threat intelligence",
                    "completed": "Threat intelligence returned",
                    "optional": True,
                }
            )

    return plan[:max_steps]


def _next_sequence(session: Session, execution_id: str) -> int:
    """Return the next available sequence number for an execution."""
    last = session.exec(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.sequence.desc())
    ).first()
    return (last.sequence + 1) if last else 1


class SubagentSpawner:
    """Spawn and manage Devin-like subagents."""

    def __init__(self, store: EventStore | None = None):
        self.store = store or event_store
        self._threads: dict[str, Thread] = {}
        self._parent_event_locks: dict[str, Lock] = {}
        self._global_lock = Lock()

    def _parent_lock(self, parent_execution_id: str) -> Lock:
        with self._global_lock:
            if parent_execution_id not in self._parent_event_locks:
                self._parent_event_locks[parent_execution_id] = Lock()
            return self._parent_event_locks[parent_execution_id]

    def _emit_parent_event(
        self,
        session: Session,
        parent_execution_id: str,
        event_type: str,
        label: str,
        payload: dict[str, Any],
    ) -> ExecutionEventPayload:
        with self._parent_lock(parent_execution_id):
            sequence = _next_sequence(session, parent_execution_id)
            return self.store.emit(
                session,
                parent_execution_id,
                sequence,
                event_type,
                label=label,
                payload=payload,
            )

    def _nesting_depth(self, session: Session, parent_execution_id: str) -> int:
        """Return the nesting depth of a parent execution."""
        parent_sub = session.exec(
            select(SubagentExecution)
            .where(SubagentExecution.child_execution_id == parent_execution_id)
        ).first()
        if parent_sub:
            return parent_sub.nesting_depth + 1
        return 0

    def spawn(
        self,
        session: Session,
        task: str,
        profile_id: str,
        parent_execution_id: str,
        incident_id: str = "",
        mode: str = "background",
    ) -> SubagentExecution:
        """Create and start a subagent execution."""
        profile = get_subagent_profile(profile_id)
        if profile is None:
            raise ValueError(f"Unknown subagent profile: {profile_id}")

        if mode not in ("foreground", "background"):
            raise ValueError(f"Invalid mode: {mode}")

        nesting_depth = self._nesting_depth(session, parent_execution_id)
        if nesting_depth > profile.max_nesting:
            raise ValueError(
                f"Max nesting depth {profile.max_nesting} exceeded for profile {profile_id}"
            )

        subagent_id = f"sub-{uuid4().hex[:12]}"
        title = task[:120] if task else "Untitled subagent"

        agent_profile = profile.to_agent_profile()
        orchestrator = AgentOrchestrator(
            session, profile_id=agent_profile.id, model_id=agent_profile.model_name
        )
        child_execution_id = orchestrator.start(
            task, incident_id=incident_id, provider="anvaya"
        )

        sub = SubagentExecution(
            subagent_id=subagent_id,
            parent_execution_id=parent_execution_id,
            child_execution_id=child_execution_id,
            profile_id=profile_id,
            title=title,
            task=task,
            mode=mode,
            status="pending",
            nesting_depth=nesting_depth,
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)

        self._emit_parent_event(
            session,
            parent_execution_id,
            "subagent.spawned",
            f"Subagent {profile.name} spawned",
            {
                "subagent_id": subagent_id,
                "profile_id": profile_id,
                "task": task,
                "mode": mode,
                "child_execution_id": child_execution_id,
            },
        )

        if mode == "foreground":
            self._run(session, sub, profile, agent_profile, task, incident_id, child_execution_id)
        else:
            thread = Thread(
                target=self._run_with_session,
                args=(subagent_id, profile, agent_profile, task, incident_id, child_execution_id),
                daemon=True,
                name=f"subagent-{subagent_id}",
            )
            self._threads[subagent_id] = thread
            thread.start()

        session.refresh(sub)
        return sub

    def _run_with_session(
        self,
        subagent_id: str,
        profile: SubagentProfile,
        agent_profile: AgentProfile,
        task: str,
        incident_id: str,
        child_execution_id: str,
    ) -> None:
        """Run a subagent in its own database session."""
        from anvaya.db import engine

        with Session(engine) as session:
            attached = session.exec(
                select(SubagentExecution).where(SubagentExecution.subagent_id == subagent_id)
            ).first()
            if attached is None:
                logger.warning("subagent.missing_in_session", subagent_id=subagent_id)
                return
            self._run(
                session,
                attached,
                profile,
                agent_profile,
                task,
                incident_id,
                child_execution_id,
            )

    def _run(
        self,
        session: Session,
        sub: SubagentExecution,
        profile: SubagentProfile,
        agent_profile: AgentProfile,
        task: str,
        incident_id: str,
        child_execution_id: str,
    ) -> None:
        """Run the subagent execution."""
        started = perf_counter()
        try:
            sub.status = "running"
            sub.started_at = datetime.now(timezone.utc)
            session.add(sub)
            session.commit()

            self._emit_parent_event(
                session,
                sub.parent_execution_id,
                "subagent.started",
                f"Subagent {profile.name} started",
                {
                    "subagent_id": sub.subagent_id,
                    "child_execution_id": child_execution_id,
                    "mode": sub.mode,
                },
            )

            plan = build_subagent_plan(session, task, incident_id, profile.allowed_tools)
            orchestrator = AgentOrchestrator(
                session,
                profile_id=agent_profile.id,
                model_id=agent_profile.model_name,
            )
            execution = orchestrator.run(
                child_execution_id,
                objective=task,
                incident_id=incident_id,
                plan=plan,
                profile=agent_profile,
            )

            session.refresh(sub)
            if sub.status == "cancelled":
                return

            tool_count = len(
                session.exec(
                    select(ExecutionEvent)
                    .where(ExecutionEvent.execution_id == child_execution_id)
                    .where(ExecutionEvent.type.in_(["tool.completed", "tool.failed"]))
                ).all()
            )

            now = datetime.now(timezone.utc)
            sub.status = execution.status
            sub.completed_at = now
            sub.duration_ms = round((perf_counter() - started) * 1000, 2)
            sub.tool_calls_count = tool_count
            sub.result_summary = execution.result_summary
            sub.error_message = execution.error_message
            session.add(sub)
            session.commit()

            self._emit_parent_event(
                session,
                sub.parent_execution_id,
                "subagent.completed" if execution.status == "completed" else "subagent.failed",
                f"Subagent {profile.name} {execution.status}",
                {
                    "subagent_id": sub.subagent_id,
                    "child_execution_id": child_execution_id,
                    "status": execution.status,
                    "duration_ms": sub.duration_ms,
                    "tool_calls_count": sub.tool_calls_count,
                    "result_summary": execution.result_summary,
                    "error_message": execution.error_message,
                },
            )
        except Exception as exc:
            logger.error("subagent.run_error", subagent_id=sub.subagent_id, error=str(exc))
            now = datetime.now(timezone.utc)
            sub.status = "failed"
            sub.completed_at = now
            sub.duration_ms = round((perf_counter() - started) * 1000, 2)
            sub.error_message = str(exc)
            session.add(sub)
            session.commit()

            self._emit_parent_event(
                session,
                sub.parent_execution_id,
                "subagent.failed",
                f"Subagent {profile.name} failed",
                {
                    "subagent_id": sub.subagent_id,
                    "child_execution_id": child_execution_id,
                    "error_message": str(exc),
                },
            )

    def cancel(self, session: Session, subagent_id: str) -> SubagentExecution:
        """Cancel/park a running or pending subagent."""
        sub = session.exec(
            select(SubagentExecution).where(SubagentExecution.subagent_id == subagent_id)
        ).first()
        if not sub:
            raise ValueError(f"Subagent {subagent_id} not found")
        if sub.status not in ("pending", "running"):
            raise ValueError(f"Cannot cancel subagent in status {sub.status}")
        sub.status = "cancelled"
        session.add(sub)
        session.commit()

        self._emit_parent_event(
            session,
            sub.parent_execution_id,
            "subagent.cancelled",
            f"Subagent {sub.profile_id} cancelled",
            {
                "subagent_id": subagent_id,
                "child_execution_id": sub.child_execution_id,
            },
        )
        session.refresh(sub)
        return sub

    def resume(
        self,
        session: Session,
        subagent_id: str,
        task: str | None = None,
    ) -> SubagentExecution:
        """Resume a cancelled, failed, or completed subagent in the foreground."""
        sub = session.exec(
            select(SubagentExecution).where(SubagentExecution.subagent_id == subagent_id)
        ).first()
        if not sub:
            raise ValueError(f"Subagent {subagent_id} not found")

        profile = get_subagent_profile(sub.profile_id)
        if profile is None:
            raise ValueError(f"Unknown subagent profile: {sub.profile_id}")

        new_task = task if task else sub.task
        return self.spawn(
            session,
            task=new_task,
            profile_id=sub.profile_id,
            parent_execution_id=sub.parent_execution_id,
            incident_id=sub.child_execution_id or "",
            mode="foreground",
        )

    def list(
        self,
        session: Session,
        parent_execution_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> Sequence[SubagentExecution]:
        """List subagent executions."""
        stmt = select(SubagentExecution)
        if parent_execution_id:
            stmt = stmt.where(SubagentExecution.parent_execution_id == parent_execution_id)
        if status:
            stmt = stmt.where(SubagentExecution.status == status)
        stmt = stmt.order_by(desc(SubagentExecution.started_at)).limit(limit)  # type: ignore[arg-type]
        return session.exec(stmt).all()

    def get(self, session: Session, subagent_id: str) -> SubagentExecution | None:
        """Get a single subagent execution."""
        return session.exec(
            select(SubagentExecution).where(SubagentExecution.subagent_id == subagent_id)
        ).first()


subagent_spawner = SubagentSpawner()
