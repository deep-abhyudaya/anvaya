"""Golden tests for the adaptive agentic investigation loop."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DEBUG"] = "false"

    import importlib

    import anvaya.config
    import anvaya.db
    import anvaya.main

    importlib.reload(anvaya.config)
    importlib.reload(anvaya.db)
    importlib.reload(anvaya.main)

    from anvaya.db import init_db
    from anvaya.main import app

    init_db()
    with TestClient(app) as c:
        yield c
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


def _create_incident(client: TestClient) -> str:
    """Create an incident and return incident_id."""
    response = client.post(
        "/api/v1/incidents",
        json={
            "title": "Adaptive mission test",
            "severity": "high",
            "attack_family": "lateral_movement",
            "host": "WS-001",
            "user": "eve",
        },
    )
    assert response.status_code == 200
    return response.json()["incident_id"]


def _seed_telemetry(client: TestClient, incident_id: str) -> None:
    """Create synthetic attack telemetry for the incident."""
    from datetime import datetime, timezone

    from anvaya.db import engine
    from anvaya.models.enums import TelemetryEventType
    from anvaya.models.graph import GraphEdge, GraphNode
    from anvaya.models.telemetry import TelemetryEvent

    with Session(engine) as session:
        base_time = datetime.now(timezone.utc)
        events = [
            TelemetryEvent(
                event_id="EVT-LOGIN",
                incident_id=incident_id,
                event_type=TelemetryEventType.AUTH_LOGIN,
                timestamp=base_time,
                actor="eve",
                host="WS-001",
                source="WS-001",
                destination="DC-01",
                process="sshd",
                is_off_hours=True,
                is_new_device=True,
                is_attack=True,
                attack_family="lateral_movement",
            ),
            TelemetryEvent(
                event_id="EVT-LATERAL",
                incident_id=incident_id,
                event_type=TelemetryEventType.LATERAL_MOVE,
                timestamp=base_time,
                actor="eve",
                host="WS-001",
                source="WS-001",
                destination="SERVER-09",
                process="psexec",
                is_lateral_movement=True,
                is_attack=True,
                attack_family="lateral_movement",
            ),
            TelemetryEvent(
                event_id="EVT-PRIV",
                incident_id=incident_id,
                event_type=TelemetryEventType.PRIVILEGE_CHANGE,
                timestamp=base_time,
                actor="eve",
                host="SERVER-09",
                source="SERVER-09",
                destination="DC-01",
                process="mimikatz",
                is_privilege_escalation=True,
                is_attack=True,
                attack_family="lateral_movement",
            ),
        ]
        for e in events:
            session.add(e)

        nodes = [
            GraphNode(
                node_id="WS-001",
                incident_id=incident_id,
                label="WS-001",
                node_type="host",
                is_compromised=True,
                impact_score=0.8,
            ),
            GraphNode(
                node_id="SERVER-09",
                incident_id=incident_id,
                label="SERVER-09",
                node_type="host",
                is_compromised=True,
                impact_score=0.9,
            ),
            GraphNode(
                node_id="DC-01",
                incident_id=incident_id,
                label="DC-01",
                node_type="host",
                is_critical=True,
                impact_score=0.95,
            ),
        ]
        for n in nodes:
            session.add(n)

        edges = [
            GraphEdge(
                source_node_id="WS-001",
                target_node_id="SERVER-09",
                incident_id=incident_id,
                edge_type="attack_path",
                is_observed=True,
            ),
            GraphEdge(
                source_node_id="SERVER-09",
                target_node_id="DC-01",
                incident_id=incident_id,
                edge_type="attack_path",
                is_observed=True,
            ),
        ]
        for edge in edges:
            session.add(edge)

        session.commit()


def test_adaptive_mission_reaches_verified_finding(client: TestClient) -> None:
    """A realistic attack trail should drive the agent to a verified finding."""
    incident_id = _create_incident(client)
    _seed_telemetry(client, incident_id)

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]
    assert data["status"] == "completed"

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    events = response.json()["items"]
    types = [e["type"] for e in events]

    assert "agent.started" in types
    assert "agent.plan_created" in types
    assert "agent.decision_started" in types
    assert "agent.tool_requested" in types
    assert "agent.observation_created" in types

    tool_names = [
        e.get("tool_name") for e in events if e["type"] in ("tool.started", "tool.completed")
    ]
    assert "observe_environment" in tool_names
    assert "detect_anomalies" in tool_names
    assert "correlate_entities" in tool_names
    assert "investigate_entity" in tool_names
    assert "trace_attack_path" in tool_names
    assert "reconstruct_timeline" in tool_names

    assert "agent.verification_passed" in types
    assert "agent.completed" in types

    response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
    assert response.status_code == 200
    context = response.json()
    assert context["status"] == "completed"
    assert len(context["findings"]) > 0
    assert any("eve" in str(f) or "SERVER-09" in str(f) for f in context["findings"])
    assert context["verification"].get("passed") is True
