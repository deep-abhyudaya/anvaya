"""Adversarial unit tests for the adaptive DecisionEngine.

These tests prove the decision engine is not a hardcoded script by showing that
small changes in blackboard, memory, or world state change the selected next
action.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from anvaya.agent.blackboard import Blackboard, Hypothesis
from anvaya.agent.decision import DecisionEngine
from anvaya.agent.mission import Mission
from anvaya.agent.world import WorldObserver
from sqlmodel import Session


@pytest.fixture
def engine_and_session():
    from sqlmodel import SQLModel, create_engine

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        from anvaya.db import init_db

        init_db()
        yield engine, session
    SQLModel.metadata.drop_all(engine)


def test_different_next_test_produces_different_tool(engine_and_session):
    """Decision must change when the leading hypothesis's next_test changes."""
    _, session = engine_and_session
    world = WorldObserver(session)
    engine = DecisionEngine(world)
    mission = Mission(objective="Investigate INC-TEST", incident_id="INC-TEST")
    bb = Blackboard(goal="test")
    bb.add_completed_action("observe_environment")
    bb.add_completed_action("observe_environment")
    h = Hypothesis(
        id="SERVER-09",
        statement="SERVER-09 is suspicious",
        confidence=0.8,
        entity_id="SERVER-09",
        next_test="correlate_entities",
    )
    bb.add_hypothesis(h)
    bb.current_candidate = "SERVER-09"

    d1 = engine.decide(mission, bb, {}, None, {})
    h.next_test = "investigate_entity"
    d2 = engine.decide(mission, bb, {}, None, {})

    assert d1.tool == "correlate_entities"
    assert d2.tool == "investigate_entity"
    assert d1.tool != d2.tool


def test_rejected_candidate_switches_to_next_hypothesis(engine_and_session):
    """Rejecting the leading candidate should make the engine switch to the next."""
    _, session = engine_and_session
    world = WorldObserver(session)
    engine = DecisionEngine(world)
    mission = Mission(objective="Investigate INC-TEST", incident_id="INC-TEST")
    bb = Blackboard(goal="test")
    bb.add_completed_action("observe_environment")
    h1 = Hypothesis(
        id="SERVER-09",
        statement="SERVER-09 is suspicious",
        confidence=0.9,
        entity_id="SERVER-09",
        next_test="correlate_entities",
        status="rejected",
    )
    h2 = Hypothesis(
        id="WS-001",
        statement="WS-001 is suspicious",
        confidence=0.7,
        entity_id="WS-001",
        next_test="investigate_entity",
    )
    bb.add_hypothesis(h1)
    bb.add_hypothesis(h2)
    bb.current_candidate = "SERVER-09"

    d = engine.decide(mission, bb, {}, None, {})
    assert d.tool == "investigate_entity"
    assert d.inputs.get("entity_id") == "WS-001"


def test_conflicting_close_confidence_triggers_comparison(engine_and_session):
    """Two close-confidence hypotheses with no clear next step should lead to test_hypothesis."""
    _, session = engine_and_session
    world = WorldObserver(session)
    engine = DecisionEngine(world)
    mission = Mission(objective="Investigate INC-TEST", incident_id="INC-TEST")
    bb = Blackboard(goal="test")
    bb.add_completed_action("observe_environment")
    h1 = Hypothesis(
        id="SERVER-09",
        statement="SERVER-09 is suspicious",
        confidence=0.62,
        entity_id="SERVER-09",
        next_test="",
    )
    h2 = Hypothesis(
        id="WS-001",
        statement="WS-001 is suspicious",
        confidence=0.55,
        entity_id="WS-001",
        next_test="",
    )
    bb.add_hypothesis(h1)
    bb.add_hypothesis(h2)
    bb.current_candidate = "SERVER-09"

    d = engine.decide(mission, bb, {}, None, {})
    assert d.tool == "test_hypothesis"
    assert d.inputs.get("entity_id") == "SERVER-09"


def test_memory_with_named_entity_skips_broad_detection(engine_and_session):
    """If the objective names an entity and memory contains a prior finding, the engine
    should investigate that entity directly instead of running detect_anomalies."""
    _, session = engine_and_session
    world = WorldObserver(session)
    engine = DecisionEngine(world)
    mission = Mission(objective="Investigate HOST-17", incident_id="INC-TEST")
    bb = Blackboard(goal="test")
    bb.add_completed_action("observe_environment")
    memory = {
        "episodic": [
            {
                "execution_id": "exec-old",
                "objective": "Investigate HOST-17",
                "status": "completed",
                "result_summary": "Finding: HOST-17 is high risk (confidence 0.85)",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    }

    d = engine.decide(mission, bb, {}, None, memory)
    assert d.tool == "investigate_entity"
    assert d.inputs.get("entity_id") == "HOST-17"


def test_no_graph_prefers_reconstruct_timeline_over_trace(engine_and_session):
    """When the world has no graph nodes, trace_attack_path should be avoided."""
    from anvaya.models.incident import Incident

    engine, session = engine_and_session
    session.add(
        Incident(
            incident_id="INC-TEST",
            title="test",
            severity="high",
            attack_family="lateral_movement",
        )
    )
    session.commit()

    world = WorldObserver(session)
    decision_engine = DecisionEngine(world)
    mission = Mission(objective="Investigate INC-TEST", incident_id="INC-TEST")
    bb = Blackboard(goal="test")
    bb.add_completed_action("observe_environment")
    h = Hypothesis(
        id="SERVER-09",
        statement="SERVER-09 is suspicious",
        confidence=0.9,
        entity_id="SERVER-09",
        next_test="trace_attack_path",
    )
    bb.add_hypothesis(h)
    bb.current_candidate = "SERVER-09"
    bb.add_completed_action("correlate_entities:SERVER-09")
    bb.add_completed_action("investigate_entity:SERVER-09")

    d = decision_engine.decide(mission, bb, {}, None, {})
    assert d.tool != "trace_attack_path"
    assert d.tool in ("reconstruct_timeline", "get_telemetry")


def test_completed_next_test_advances_in_chain(engine_and_session):
    """If the hypothesis's next_test is already completed, the engine falls forward."""
    _, session = engine_and_session
    world = WorldObserver(session)
    engine = DecisionEngine(world)
    mission = Mission(objective="Investigate INC-TEST", incident_id="INC-TEST")
    bb = Blackboard(goal="test")
    bb.add_completed_action("observe_environment")
    h = Hypothesis(
        id="SERVER-09",
        statement="SERVER-09 is suspicious",
        confidence=0.9,
        entity_id="SERVER-09",
        next_test="correlate_entities",
    )
    bb.add_hypothesis(h)
    bb.current_candidate = "SERVER-09"
    bb.add_completed_action("correlate_entities:SERVER-09")

    d = engine.decide(mission, bb, {}, None, {})
    assert d.tool == "investigate_entity"
