"""Behavioral contract tests for the frontier agent loop.

These tests verify the core contracts of the frontier model-driven
iterative execution engine without requiring real model API calls.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from anvaya.agent.blackboard import Blackboard
from anvaya.agent.events import EventStore
from anvaya.agent.frontier_decision import (
    FrontierDecisionEngine,
    NextActionContract,
    build_model_context,
)
from anvaya.agent.frontier_loop import run_frontier
from anvaya.agent.mission import Mission
from anvaya.agent.scope import ScopeConstraints, enforce_scope, parse_scope
from anvaya.agent.verification import VerificationResult, verify_action_completion
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution, ExecutionEvent




@pytest.fixture(scope="function")
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    SQLModel.metadata.drop_all(engine)


def _make_model(quality_class: str = "frontier") -> MagicMock:
    model = MagicMock()
    model.id = "test-frontier"
    model.provider = "test"
    model.display_name = "Test Frontier"
    model.quality_class = quality_class
    model.default_temperature = 0.1
    model.model_name = "test-frontier"
    return model


def _make_provider(*responses: dict[str, Any]) -> MagicMock:
    """Create a mock provider that returns canned responses in sequence."""
    provider = MagicMock()
    provider.name = "test"
    provider.configured.return_value = True

    call_idx = {"n": 0}
    response_list = list(responses) if responses else [
        {"action": "finish", "reason": "Done.", "summary": "Finished."},
    ]

    def _chat_completion(messages, **kwargs):
        idx = min(call_idx["n"], len(response_list) - 1)
        call_idx["n"] += 1
        resp = MagicMock()
        resp.to_dict.return_value = {"text": json.dumps(response_list[idx])}
        return resp

    provider.chat_completion = _chat_completion
    return provider


def _events_of_type(session: Session, execution_id: str, event_type: str) -> list[ExecutionEvent]:
    return list(
        session.exec(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
            .where(ExecutionEvent.type == event_type)
            .order_by(ExecutionEvent.sequence.asc())
        ).all()
    )


def _all_events(session: Session, execution_id: str) -> list[ExecutionEvent]:
    return list(
        session.exec(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
            .order_by(ExecutionEvent.sequence.asc())
        ).all()
    )




class TestNextActionContract:
    def test_parse_tool_action(self):
        contract = NextActionContract(
            action="detect_anomalies",
            inputs={"incident_id": "INC-001"},
            reason="Need to detect anomalies first.",
        )
        assert contract.action == "detect_anomalies"
        assert contract.inputs["incident_id"] == "INC-001"

    def test_parse_finish_action(self):
        contract = NextActionContract(
            action="finish",
            reason="All tasks done.",
            summary="Investigation complete.",
        )
        assert contract.action == "finish"
        assert contract.summary == "Investigation complete."

    def test_parse_replan_action(self):
        contract = NextActionContract(
            action="replan",
            reason="Need different approach.",
            plan_update=[{"tool": "get_telemetry", "status": "pending"}],
        )
        assert contract.action == "replan"
        assert len(contract.plan_update) == 1




class TestScopeEnforcement:
    def test_parse_only_orbits(self):
        scope = parse_scope("Create only orbits")
        assert scope.mode == "only"
        assert scope.allowed_artifacts == ["orbits"]

    def test_parse_orbits_and_reach(self):
        scope = parse_scope("Generate orbits and reach")
        assert scope.mode == "explicit"
        assert "orbits" in scope.allowed_artifacts
        assert "reach" in scope.allowed_artifacts

    def test_parse_everything(self):
        scope = parse_scope("Generate everything")
        assert scope.mode == "all"

    def test_parse_investigation_no_artifacts(self):
        scope = parse_scope("Analyze the login anomalies on host WS-001")
        assert scope.mode == "all"

    def test_enforce_scope_filters(self):
        scope = ScopeConstraints(allowed_artifacts=["orbits"], mode="only")
        inputs = {"requested_artifacts": ["orbits", "reach", "segments"]}
        result = enforce_scope("generate_artifacts", inputs, scope)
        assert result["requested_artifacts"] == ["orbits"]

    def test_enforce_scope_passthrough_non_artifact_tool(self):
        scope = ScopeConstraints(allowed_artifacts=["orbits"], mode="only")
        inputs = {"incident_id": "INC-001"}
        result = enforce_scope("detect_anomalies", inputs, scope)
        assert result == inputs

    def test_enforce_scope_all_mode(self):
        scope = ScopeConstraints(mode="all")
        inputs = {"requested_artifacts": ["orbits", "reach"]}
        result = enforce_scope("generate_artifacts", inputs, scope)
        assert result["requested_artifacts"] == ["orbits", "reach"]

    def test_scope_constraint_strings(self):
        scope = ScopeConstraints(allowed_artifacts=["orbits", "reach"], mode="only")
        strings = scope.to_constraint_strings()
        assert "only:orbits" in strings
        assert "only:reach" in strings




class TestMissionBudget:
    def test_model_calls_budget(self):
        mission = Mission(max_model_calls=3)
        assert mission.is_within_budget()
        mission.model_calls = 3
        assert not mission.is_within_budget()

    def test_model_step_increments(self):
        mission = Mission()
        assert mission.model_calls == 0
        mission.model_step()
        assert mission.model_calls == 1

    def test_constraints_stored(self):
        mission = Mission(constraints=["only:orbits"], allowed_artifacts=["orbits"])
        assert mission.constraints == ["only:orbits"]
        assert mission.allowed_artifacts == ["orbits"]

    def test_should_continue_respects_model_calls(self):
        mission = Mission(max_model_calls=2)
        mission.model_calls = 2
        assert not mission.should_continue()




class TestVerifyActionCompletion:
    def test_success_tool_passes(self):
        result = MagicMock()
        result.status = "success"
        result.output = {"created": {"orbits": True}}
        result.artifact_refs = [MagicMock()]
        result.output_summary = "Orbits generated"
        vr = verify_action_completion("generate_artifacts", result, "Orbits saved")
        assert vr.passed

    def test_failed_tool_fails_verification(self):
        result = MagicMock()
        result.status = "error"
        result.output = {}
        result.artifact_refs = []
        result.output_summary = ""
        vr = verify_action_completion("generate_artifacts", result, "")
        assert not vr.passed
        assert "tool_returned_error" in vr.missing

    def test_no_artifacts_created(self):
        result = MagicMock()
        result.status = "success"
        result.output = {}
        result.artifact_refs = []
        result.output_summary = "No artifacts"
        vr = verify_action_completion("generate_artifacts", result, "")
        assert not vr.passed
        assert "no_artifacts_created" in vr.missing




class TestBlackboardExtensions:
    def test_artifact_state_tracking(self):
        bb = Blackboard(goal="test")
        bb.update_artifact_state("orbits", "generating")
        assert bb.artifact_state["orbits"] == "generating"
        bb.update_artifact_state("orbits", "saved")
        assert bb.artifact_state["orbits"] == "saved"

    def test_scope_constraints_field(self):
        bb = Blackboard(goal="test", scope_constraints=["only:orbits"])
        assert bb.scope_constraints == ["only:orbits"]




class TestFrontierDecisionEngine:
    def test_finish_action_returned(self):
        model = _make_model()

        finish_response = json.dumps(
            {"action": "finish", "reason": "Done.", "summary": "Complete."}
        )
        provider = MagicMock()
        provider.name = "test"
        provider.configured.return_value = True

        class FakeResponse:
            def to_dict(self):
                return {"text": finish_response}

        provider.chat_completion.return_value = FakeResponse()

        engine = FrontierDecisionEngine(provider, model)
        mission = Mission(objective="test")

        context = MagicMock()
        context.plan = []
        context.observations = []
        context.messages = []
        context.reasoning_summary = ""
        context.objective = "test"
        context.incident_id = ""
        context.project_id = ""
        context.status = "running"
        bb = Blackboard(goal="test")

        contract = engine.decide(
            mission=mission,
            context=context,
            blackboard=bb,
        )
        assert contract.action == "finish"
        assert contract.summary == "Complete."

    def test_retry_tracking(self):
        model = _make_model()
        provider = _make_provider()
        engine = FrontierDecisionEngine(provider, model)
        assert engine.get_retry_count("tool_a", "key1") == 0
        engine.track_retry("tool_a", "key1")
        assert engine.get_retry_count("tool_a", "key1") == 1
        engine.track_retry("tool_a", "key1")
        assert engine.get_retry_count("tool_a", "key1") == 2

    def test_model_failure_returns_finish(self):
        model = _make_model()
        provider = MagicMock()
        provider.name = "test"
        provider.chat_completion.side_effect = RuntimeError("API down")
        engine = FrontierDecisionEngine(provider, model)
        mission = Mission(objective="test")
        context = MagicMock(spec=ExecutionContext)
        context.plan = []
        bb = Blackboard(goal="test")

        contract = engine.decide(
            mission=mission,
            context=context,
            blackboard=bb,
        )
        assert contract.action == "finish"
        assert "failed" in contract.reason.lower()




class TestBuildModelContext:
    def test_contains_mission(self):
        mission = Mission(objective="Investigate INC-001")
        context = MagicMock(spec=ExecutionContext)
        context.plan = []
        bb = Blackboard(goal="test")

        text = build_model_context(
            mission=mission,
            context=context,
            blackboard=bb,
            available_tools=[],
        )
        assert "MISSION" in text
        assert "Investigate INC-001" in text

    def test_contains_tools(self):
        mission = Mission(objective="test")
        context = MagicMock(spec=ExecutionContext)
        context.plan = []
        bb = Blackboard(goal="test")

        text = build_model_context(
            mission=mission,
            context=context,
            blackboard=bb,
            available_tools=[{"name": "detect_anomalies", "description": "Find anomalies"}],
        )
        assert "detect_anomalies" in text

    def test_contains_failures(self):
        mission = Mission(objective="test")
        context = MagicMock(spec=ExecutionContext)
        context.plan = []
        bb = Blackboard(goal="test")

        text = build_model_context(
            mission=mission,
            context=context,
            blackboard=bb,
            available_tools=[],
            recent_failures=["get_telemetry: timeout"],
        )
        assert "get_telemetry: timeout" in text




class TestEventHelpers:
    def test_emit_artifact_progress(self, session):
        from anvaya.agent.events import emit_artifact_progress

        store = EventStore()
        eid = store.create_execution(session, "test")

        emit_artifact_progress(
            store, session, eid,
            artifact_type="orbits",
            status="generating",
            progress=0.5,
            label="Building orbits",
        )

        events = _events_of_type(session, eid, "artifact.progress")
        assert len(events) == 1
        payload = json.loads(events[0].payload_json)
        assert payload["artifact_type"] == "orbits"
        assert payload["progress"] == 0.5

    def test_emit_verification(self, session):
        from anvaya.agent.events import emit_verification_event

        store = EventStore()
        eid = store.create_execution(session, "test")

        emit_verification_event(
            store, session, eid,
            passed=True,
            reason="All checks passed",
        )

        started = _events_of_type(session, eid, "agent.verification_started")
        completed = _events_of_type(session, eid, "agent.verification_completed")
        assert len(started) == 1
        assert len(completed) == 1
        payload = json.loads(completed[0].payload_json)
        assert payload["passed"] is True

    def test_emit_plan_step_update(self, session):
        from anvaya.agent.events import emit_plan_step_update

        store = EventStore()
        eid = store.create_execution(session, "test")

        emit_plan_step_update(
            store, session, eid,
            step_index=0,
            tool_name="detect_anomalies",
            new_status="completed",
            result_summary="Found 3 anomalies",
        )

        events = _events_of_type(session, eid, "agent.plan_step_update")
        assert len(events) == 1
        payload = json.loads(events[0].payload_json)
        assert payload["tool_name"] == "detect_anomalies"
        assert payload["new_status"] == "completed"




class TestFrontierLoopIntegration:
    """Integration tests that run the actual frontier loop with mocked model."""

    def _make_loop_and_execution(self, session: Session, objective: str = "Test"):
        store = EventStore()
        eid = store.create_execution(session, objective, incident_id="INC-TEST")

        execution = store.get_execution(session, eid)
        assert execution is not None

        loop = MagicMock()
        loop.session = session
        loop.store = store
        loop.executor = MagicMock()
        loop.registry = MagicMock()
        loop.registry.get.return_value = None
        loop.registry.list_tools.return_value = []
        loop.registry.validate_inputs.return_value = (True, [])

        def _get_or_create_context(**kwargs):
            existing = session.exec(
                select(ExecutionContext).where(ExecutionContext.execution_id == kwargs["execution_id"])
            ).first()
            if existing:
                return existing
            ctx = ExecutionContext(**kwargs)
            session.add(ctx)
            session.commit()
            session.refresh(ctx)
            return ctx

        loop._get_or_create_context = _get_or_create_context
        loop._save_context = lambda ctx: (session.add(ctx), session.commit())
        loop._check_messages = lambda *a: (False, "")
        loop._emit_execution_interrupted = lambda *a: None

        return loop, execution, store

    def test_finish_action_completes_execution(self, session):
        """Model returns finish → execution completes cleanly."""
        loop, execution, store = self._make_loop_and_execution(session)
        model = _make_model()
        provider = _make_provider(
            {"action": "finish", "reason": "Done.", "summary": "Test finished."},
        )
        provider.chat_completion = MagicMock(side_effect=[
            MagicMock(to_dict=MagicMock(return_value={"text": "Analyzing..."})),
            MagicMock(to_dict=MagicMock(return_value={
                "text": json.dumps({"action": "finish", "reason": "Done.", "summary": "Test finished."})
            })),
        ])

        from anvaya.agent.messaging import MessageGenerator
        from anvaya.agent.profiles import get_profile
        from anvaya.agent.memory import MemoryStore
        from anvaya.agent.world import WorldObserver

        profile = get_profile("sentinel") or get_profile("general")
        messenger = MessageGenerator(profile)
        world = MagicMock(spec=WorldObserver)
        world.observe_environment.return_value = {}
        memory = MagicMock(spec=MemoryStore)
        memory.recall.return_value = {}

        result = run_frontier(
            loop=loop,
            execution=execution,
            incident_id="INC-TEST",
            profile=profile,
            active_model=model,
            model_provider=provider,
            messenger=messenger,
            objective="Test objective",
            project_id="",
            world=world,
            memory_store=memory,
            initial_plan=[],
        )

        completed = _events_of_type(session, execution.execution_id, "agent.completed")
        assert len(completed) >= 1

        reasoning = _events_of_type(session, execution.execution_id, "agent.reasoning_started")
        assert len(reasoning) >= 1

    def test_scope_enforced_on_artifacts(self, session):
        """Scope constraints filter artifact requests."""
        scope = parse_scope("Create only orbits")
        assert scope.mode == "only"
        assert scope.allowed_artifacts == ["orbits"]

        inputs = {"requested_artifacts": ["orbits", "reach", "segments", "arena"]}
        filtered = enforce_scope("generate_artifacts", inputs, scope)
        assert filtered["requested_artifacts"] == ["orbits"]

    def test_cancellation_stops_cleanly(self, session):
        """Cancelled context stops the loop."""
        loop, execution, store = self._make_loop_and_execution(session, "Cancel test")

        model = _make_model()
        provider = _make_provider()

        from anvaya.agent.messaging import MessageGenerator
        from anvaya.agent.profiles import get_profile
        from anvaya.agent.memory import MemoryStore
        from anvaya.agent.world import WorldObserver

        profile = get_profile("sentinel") or get_profile("general")
        messenger = MessageGenerator(profile)
        world = MagicMock(spec=WorldObserver)
        world.observe_environment.return_value = {}
        memory = MagicMock(spec=MemoryStore)
        memory.recall.return_value = {}

        loop._check_messages = lambda *a: (True, "cancelled")

        result = run_frontier(
            loop=loop,
            execution=execution,
            incident_id="INC-TEST",
            profile=profile,
            active_model=model,
            model_provider=provider,
            messenger=messenger,
            objective="Cancel test",
            project_id="",
            world=world,
            memory_store=memory,
            initial_plan=[],
        )

        decisions = _events_of_type(session, execution.execution_id, "agent.decision_started")
        assert len(decisions) == 0
