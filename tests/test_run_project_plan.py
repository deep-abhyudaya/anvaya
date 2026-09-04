"""Tests for AgentLoop.run_project_plan per-artifact narration."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from anvaya.agent.agent_loop import AgentLoop
from anvaya.agent.executor import LocalToolExecutor
from anvaya.agent.orchestrator import AgentOrchestrator
from anvaya.agent.schemas import ArtifactRef, ToolResult
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.incident import Incident
from anvaya.models.project import ARTIFACT_TYPES, Project
from anvaya.routes import route_for_artifact_type
from sqlmodel import Session, select


@pytest.fixture
def test_project(db_session: Session) -> Project:
    project = Project(
        project_id=f"PRJ-{uuid4().hex[:8].upper()}",
        organization_id="ORG-1",
        name="Run Project Plan Test",
        created_by="u1",
    )
    db_session.add(project)
    db_session.commit()
    return project


@pytest.fixture
def execution(db_session: Session, test_project: Project) -> Execution:
    execution = Execution(
        execution_id=f"exec-{uuid4().hex[:12]}",
        objective="generate orbits then incidents then impact tree gallery",
        status="running",
        provider="anvaya",
    )
    db_session.add(execution)
    db_session.commit()
    return execution


@pytest.fixture
def mock_manage_artifacts(monkeypatch):
    """Return a deterministic ToolResult for every manage_artifacts call."""

    def _execute(self, tool_name: str, inputs: dict, **kwargs):
        if tool_name == "manage_artifacts":
            atype = inputs["requested_artifacts"][0]
            return ToolResult(
                tool_name="manage_artifacts",
                status="success",
                output_summary=f"Generated 1 {atype} artifact from dataset.csv",
                output={"created": {atype: 1}},
                artifact_refs=[
                    ArtifactRef(
                        ref_type=atype,
                        ref_id=f"GEN-{atype}",
                        label=f"{atype}: 1 created",
                        link=f"/projects/{inputs['project_id']}",
                    )
                ],
            )
        return ToolResult(tool_name=tool_name, status="success")

    monkeypatch.setattr(LocalToolExecutor, "execute", _execute)


def _events(db_session: Session, execution_id: str) -> list[ExecutionEvent]:
    stmt = (
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.sequence)
    )
    return list(db_session.exec(stmt).all())


def _event_types(events: list[ExecutionEvent]) -> list[str]:
    return [e.type for e in events]


def _payload(event: ExecutionEvent) -> dict:
    return json.loads(event.payload_json or "{}")


def _plan_created_payload(events: list[ExecutionEvent]) -> dict:
    for e in events:
        if e.type == "agent.plan_created":
            return _payload(e)
    return {}


def test_single_artifact_objective_emits_one_step(
    db_session: Session, test_project: Project, execution: Execution, mock_manage_artifacts
):
    """Single-artifact objective keeps the original one-step event shape."""
    orchestrator = AgentOrchestrator(db_session)
    loop = AgentLoop(orchestrator)

    loop.run_project_plan(
        execution,
        test_project.project_id,
        execution.objective,
        None,
        "generate",
        ["orbits"],
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    assert types.count("agent.plan_created") == 1
    assert types.count("agent.completed") == 1
    assert types.count("agent.failed") == 0

    payload = _plan_created_payload(events)
    plan = payload.get("plan", [])
    assert len(plan) == 1
    assert plan[0]["tool"] == "manage_artifacts"
    assert plan[0]["inputs"]["requested_artifacts"] == ["orbits"]
    assert "target_artifact_type" not in plan[0]
    assert "route" not in plan[0]

    assert types.count("agent.reasoning_started") == 1
    assert types.count("agent.reasoning_completed") == 1
    assert types.count("agent.decision_started") == 1
    assert types.count("agent.tool_requested") == 1
    assert types.count("agent.observation_created") == 1
    assert types.count("tool.completed") == 1

    assert types.count("artifact.created") == 1


def test_three_artifact_objective_narrates_per_step(
    db_session: Session, test_project: Project, execution: Execution, mock_manage_artifacts
):
    """Three requested types produce three distinct reasoning/decision/tool cycles."""
    orchestrator = AgentOrchestrator(db_session)
    loop = AgentLoop(orchestrator)

    requested = ["orbits", "incidents", "impacts"]
    loop.run_project_plan(
        execution,
        test_project.project_id,
        execution.objective,
        None,
        "generate",
        requested,
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    assert types.count("agent.plan_created") == 1
    assert types.count("agent.completed") == 1
    assert types.count("agent.failed") == 0

    payload = _plan_created_payload(events)
    plan = payload.get("plan", [])
    assert len(plan) == 3
    for i, step in enumerate(plan):
        assert step["tool"] == "manage_artifacts"
        assert step["inputs"]["requested_artifacts"] == [requested[i]]
        assert step["target_artifact_type"] == requested[i]
        assert step["route"] == route_for_artifact_type(requested[i])

    assert types.count("agent.reasoning_started") == 3
    assert types.count("agent.reasoning_completed") == 3
    assert types.count("agent.decision_started") == 3
    assert types.count("agent.tool_requested") == 3
    assert types.count("agent.observation_created") == 3
    assert types.count("tool.completed") == 3

    assert types.count("artifact.created") == 3

    decision_events = [e for e in events if e.type == "agent.decision_started"]
    assert len(decision_events) == 3
    for e in decision_events:
        p = _payload(e)
        assert "target_artifact_type" in p
        assert "route" in p

    reasoning_events = [e for e in events if e.type == "agent.reasoning_completed"]
    assert len(reasoning_events) == 3
    for i, e in enumerate(reasoning_events):
        p = _payload(e)
        summary = p.get("summary", "")
        route = route_for_artifact_type(requested[i])
        assert f"/{route}" in summary

    completed = [e for e in events if e.type == "agent.completed"][0]
    assert _payload(completed).get("status") == "completed"
    message = [e for e in events if e.type == "agent.message"][-1]
    assert _payload(message).get("message")
    for atype in requested:
        assert atype in _payload(message)["message"]


def test_generate_all_expands_to_one_step_per_artifact_type(
    db_session: Session, test_project: Project, execution: Execution, mock_manage_artifacts
):
    """'all' expands to the canonical 11 artifact types and narrates each."""
    orchestrator = AgentOrchestrator(db_session)
    loop = AgentLoop(orchestrator)

    loop.run_project_plan(
        execution,
        test_project.project_id,
        "generate all",
        None,
        "generate",
        ["all"],
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    payload = _plan_created_payload(events)
    plan = payload.get("plan", [])
    assert len(plan) == len(ARTIFACT_TYPES)
    assert [s["target_artifact_type"] for s in plan] == list(ARTIFACT_TYPES)

    assert types.count("agent.reasoning_started") == len(ARTIFACT_TYPES)
    assert types.count("agent.tool_requested") == len(ARTIFACT_TYPES)
    assert types.count("agent.observation_created") == len(ARTIFACT_TYPES)
    assert types.count("agent.completed") == 1


def test_multi_artifact_failure_stops_at_first_failed_step(
    db_session: Session, test_project: Project, execution: Execution, monkeypatch
):
    """A failing step aborts the batch and emits agent.failed."""
    calls = []

    def _execute(self, tool_name: str, inputs: dict, **kwargs):
        calls.append(tool_name)
        if tool_name == "manage_artifacts" and inputs["requested_artifacts"][0] == "incidents":
            return ToolResult(
                tool_name="manage_artifacts",
                status="failure",
                error_code="generation_failed",
                error_message="incidents build failed",
            )
        atype = inputs["requested_artifacts"][0]
        return ToolResult(
            tool_name="manage_artifacts",
            status="success",
            output_summary=f"Generated 1 {atype} artifact",
            output={"created": {atype: 1}},
            artifact_refs=[
                ArtifactRef(
                    ref_type=atype,
                    ref_id=f"GEN-{atype}",
                    label=f"{atype}: 1 created",
                    link=f"/projects/{inputs['project_id']}",
                )
            ],
        )

    monkeypatch.setattr(LocalToolExecutor, "execute", _execute)

    orchestrator = AgentOrchestrator(db_session)
    loop = AgentLoop(orchestrator)

    loop.run_project_plan(
        execution,
        test_project.project_id,
        "generate orbits then incidents then impacts",
        None,
        "generate",
        ["orbits", "incidents", "impacts"],
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    assert types.count("agent.completed") == 0
    assert types.count("agent.failed") == 1
    assert calls == ["manage_artifacts", "manage_artifacts"]

    messages = [e for e in events if e.type == "agent.message"]
    assert messages[-1].label == "Project artifact generation failed"

    failed = [e for e in events if e.type == "agent.failed"][0]
    assert _payload(failed).get("status") == "failed"
    assert "incidents build failed" in _payload(failed).get("error_message", "")


def _fake_executor_result(tool_name: str, inputs: dict) -> ToolResult:
    if tool_name == "manage_artifacts":
        atype = inputs["requested_artifacts"][0]
        return ToolResult(
            tool_name="manage_artifacts",
            status="success",
            output_summary=f"Generated 1 {atype} artifact",
            output={"created": {atype: 1}},
            artifact_refs=[
                ArtifactRef(
                    ref_type=atype,
                    ref_id=f"GEN-{atype}",
                    label=f"{atype}: 1 created",
                    link=f"/projects/{inputs['project_id']}",
                )
            ],
        )
    return ToolResult(
        tool_name=tool_name,
        status="success",
        output_summary=f"{tool_name} completed",
    )


def _patch_executor_for_mixed(monkeypatch) -> list[str]:
    calls: list[str] = []

    def _execute(self, tool_name: str, inputs: dict, **kwargs):
        calls.append(tool_name)
        return _fake_executor_result(tool_name, inputs)

    monkeypatch.setattr(LocalToolExecutor, "execute", _execute)
    return calls


@pytest.fixture
def mixed_incident(db_session: Session, test_project: Project) -> Incident:
    incident = Incident(
        incident_id="INC-MIXED",
        title="Mixed objective incident",
        severity="high",
        attack_family="lateral_movement",
        host="WS-001",
        user="eve",
    )
    db_session.add(incident)
    db_session.commit()
    return incident


def test_mixed_objective_runs_investigation_then_artifacts(
    db_session: Session,
    test_project: Project,
    mixed_incident: Incident,
    execution: Execution,
    monkeypatch,
):
    """A mixed objective produces one ordered plan with both tool families."""
    calls = _patch_executor_for_mixed(monkeypatch)

    execution.objective = (
        "investigate INC-MIXED and rebuild orbits and the impact gallery"
    )
    db_session.add(execution)
    db_session.commit()

    orchestrator = AgentOrchestrator(db_session)
    orchestrator.run(
        execution.execution_id,
        execution.objective,
        project_id=test_project.project_id,
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    assert types.count("agent.plan_created") == 1
    assert types.count("agent.completed") == 1
    assert types.count("agent.failed") == 0

    plan = _plan_created_payload(events).get("plan", [])
    tool_names = [s["tool"] for s in plan]
    assert "get_incident" in tool_names
    assert tool_names.count("manage_artifacts") == 2

    first_manage = next(
        (i for i, s in enumerate(plan) if s["tool"] == "manage_artifacts"), None
    )
    assert first_manage is not None
    assert all(
        plan[i]["tool"] != "manage_artifacts" for i in range(first_manage)
    )

    artifact_steps = [s for s in plan if s["tool"] == "manage_artifacts"]
    assert artifact_steps[0]["target_artifact_type"] == "orbits"
    assert artifact_steps[0]["route"] == route_for_artifact_type("orbits")
    assert artifact_steps[1]["target_artifact_type"] == "impacts"
    assert artifact_steps[1]["route"] == route_for_artifact_type("impacts")

    assert types.count("agent.reasoning_started") >= 2
    assert types.count("agent.decision_started") >= 2
    assert types.count("agent.tool_requested") >= 2
    assert types.count("agent.observation_created") >= 2
    assert "manage_artifacts" in calls


def test_pure_investigation_skips_artifact_steps(
    db_session: Session,
    mixed_incident: Incident,
    execution: Execution,
    monkeypatch,
):
    """A pure investigation objective is not misclassified as mixed."""
    calls = _patch_executor_for_mixed(monkeypatch)

    execution.objective = "investigate INC-MIXED"
    db_session.add(execution)
    db_session.commit()

    orchestrator = AgentOrchestrator(db_session)
    orchestrator.run(execution.execution_id, execution.objective)

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    plan = _plan_created_payload(events).get("plan", [])
    assert not any(s["tool"] == "manage_artifacts" for s in plan)
    assert types.count("agent.completed") == 1
    assert "manage_artifacts" not in calls


def test_pure_multi_artifact_runs_project_plan(
    db_session: Session,
    test_project: Project,
    execution: Execution,
    monkeypatch,
):
    """A pure multi-artifact objective still routes to run_project_plan."""
    _patch_executor_for_mixed(monkeypatch)

    execution.objective = "generate orbits then incidents then impact tree gallery"
    db_session.add(execution)
    db_session.commit()

    orchestrator = AgentOrchestrator(db_session)
    orchestrator.run(
        execution.execution_id,
        execution.objective,
        project_id=test_project.project_id,
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    plan = _plan_created_payload(events).get("plan", [])
    assert all(s["tool"] == "manage_artifacts" for s in plan)
    assert len(plan) == 4
    assert types.count("agent.completed") == 1
    assert (
        sum(
            1
            for e in events
            if e.type == "tool.started" and e.tool_name == "manage_artifacts"
        )
        == 4
    )


def test_create_nerve_arbor_routes_to_artifact_builder(
    db_session: Session,
    test_project: Project,
    execution: Execution,
    monkeypatch,
):
    """The 'create NERVE ARBOR' wording used to misroute to live build; now it runs manage_artifacts."""
    calls = _patch_executor_for_mixed(monkeypatch)

    execution.objective = "create NERVE ARBOR"
    db_session.add(execution)
    db_session.commit()

    orchestrator = AgentOrchestrator(db_session)
    orchestrator.run(
        execution.execution_id,
        execution.objective,
        project_id=test_project.project_id,
    )

    events = _events(db_session, execution.execution_id)
    types = _event_types(events)

    assert "live_build" not in calls
    assert types.count("agent.failed") == 0
    assert types.count("agent.completed") == 1

    plan = _plan_created_payload(events).get("plan", [])
    assert all(s["tool"] == "manage_artifacts" for s in plan)
    assert len(plan) == 1
    assert plan[0]["inputs"]["requested_artifacts"] == ["arbor"]
    assert "target_artifact_type" not in plan[0]
    assert calls == ["manage_artifacts"]


def test_continue_artifact_execution_reuses_same_execution(
    db_session: Session,
    test_project: Project,
    execution: Execution,
    monkeypatch,
):
    """A second artifact command can re-run the same execution instead of creating a new conversation."""
    calls = _patch_executor_for_mixed(monkeypatch)

    orchestrator = AgentOrchestrator(db_session)

    execution.objective = "generate incidents"
    db_session.add(execution)
    db_session.commit()
    orchestrator.run(
        execution.execution_id,
        execution.objective,
        project_id=test_project.project_id,
    )

    execution_id = execution.execution_id
    first_events = _events(db_session, execution_id)
    assert [e for e in first_events if e.type == "agent.completed"]

    orchestrator.run(
        execution_id,
        "generate orbits",
        project_id=test_project.project_id,
    )

    all_events = _events(db_session, execution_id)
    types = _event_types(all_events)
    assert types.count("agent.completed") == 2
    assert types.count("agent.plan_created") == 2
    assert calls == ["manage_artifacts", "manage_artifacts"]

    assert execution.execution_id == execution_id
    assert execution.objective == "generate orbits"
