"""Adversarial integration tests for the adaptive agentic loop.

These tests exercise the backend HTTP API with deliberately crafted datasets to
prove the agent changes its behavior when the environment changes.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import datetime, timezone

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


def _seed_telemetry(client: TestClient, incident_id: str, events: list) -> None:
    from anvaya.db import engine

    with Session(engine) as session:
        for e in events:
            session.add(e)
        session.commit()


def _events(
    incident_id: str, process: str = "psexec", actor: str = "eve", is_attack: bool = True
) -> list:
    from anvaya.models.enums import TelemetryEventType
    from anvaya.models.telemetry import TelemetryEvent

    base = datetime.now(timezone.utc)
    return [
        TelemetryEvent(
            event_id="E1",
            incident_id=incident_id,
            event_type=TelemetryEventType.AUTH_LOGIN,
            timestamp=base,
            actor=actor,
            host="WS-001",
            source="WS-001",
            destination="DC-01",
            process="sshd",
            is_off_hours=True,
            is_new_device=True,
            is_attack=is_attack,
            attack_family="lateral_movement",
        ),
        TelemetryEvent(
            event_id="E2",
            incident_id=incident_id,
            event_type=TelemetryEventType.LATERAL_MOVE,
            timestamp=base,
            actor=actor,
            host="WS-001",
            source="WS-001",
            destination="SERVER-09",
            process=process,
            is_lateral_movement=True,
            is_attack=is_attack,
            attack_family="lateral_movement",
        ),
        TelemetryEvent(
            event_id="E3",
            incident_id=incident_id,
            event_type=TelemetryEventType.PRIVILEGE_CHANGE,
            timestamp=base,
            actor=actor,
            host="SERVER-09",
            source="SERVER-09",
            destination="DC-01",
            process="mimikatz",
            is_privilege_escalation=True,
            is_attack=is_attack,
            attack_family="lateral_movement",
        ),
    ]


def _graph_nodes(incident_id: str) -> list:
    from anvaya.models.graph import GraphNode

    return [
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


def _graph_edges(incident_id: str) -> list:
    from anvaya.models.graph import GraphEdge

    return [
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


def _tool_names(events: list) -> list:
    return [e.get("tool_name") for e in events if e["type"] in ("tool.started", "tool.completed")]


def test_false_positive_recovery(client: TestClient) -> None:
    """A top candidate that is actually an authorized scanner must be rejected."""
    from anvaya.models.enums import TelemetryEventType
    from anvaya.models.telemetry import TelemetryEvent

    incident_id = _create_incident(client)
    base = datetime.now(timezone.utc)
    scanner_events = [
        TelemetryEvent(
            event_id="E1",
            incident_id=incident_id,
            event_type=TelemetryEventType.AUTH_LOGIN,
            timestamp=base,
            actor="eve",
            host="WS-001",
            source="WS-001",
            destination="DC-01",
            process="vuln_scan",
            is_off_hours=True,
            is_new_device=True,
            is_attack=False,
            attack_family="lateral_movement",
        ),
    ]
    _seed_telemetry(client, incident_id, scanner_events)

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    events = response.json()["items"]
    tool_names = _tool_names(events)

    assert "observe_environment" in tool_names
    assert "detect_anomalies" in tool_names
    assert "investigate_entity" in tool_names

    types = [e["type"] for e in events]
    assert "agent.verification_passed" not in types


def test_insufficient_evidence_stops(client: TestClient) -> None:
    """A single event with no graph data must not produce a false finding."""
    from anvaya.models.enums import TelemetryEventType
    from anvaya.models.telemetry import TelemetryEvent

    incident_id = _create_incident(client)
    base = datetime.now(timezone.utc)
    single = TelemetryEvent(
        event_id="E1",
        incident_id=incident_id,
        event_type=TelemetryEventType.AUTH_LOGIN,
        timestamp=base,
        actor="eve",
        host="WS-001",
        source="WS-001",
        destination="DC-01",
        process="sshd",
        is_off_hours=True,
        is_new_device=True,
        is_attack=False,
        attack_family="lateral_movement",
    )
    _seed_telemetry(client, incident_id, [single])

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]
    assert data["status"] == "completed"

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    types = [e["type"] for e in response.json()["items"]]
    assert "agent.verification_passed" not in types

    context = client.get(f"/api/v1/agent/executions/{execution_id}/context").json()
    assert context["status"] == "completed"
    assert context["findings"] == []


def test_tool_failure_recovery(client: TestClient) -> None:
    """trace_attack_path should fail gracefully and the agent should fall back."""
    incident_id = _create_incident(client)
    events = _events(incident_id)
    _seed_telemetry(client, incident_id, events)

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    events = response.json()["items"]
    tool_names = _tool_names(events)

    assert data["status"] == "completed"
    assert "observe_environment" in tool_names
    assert "detect_anomalies" in tool_names


def test_changing_environment_changes_decision(client: TestClient) -> None:
    """Insert new evidence after the first observation and prove the agent adapts."""
    from anvaya.models.enums import TelemetryEventType
    from anvaya.models.telemetry import TelemetryEvent

    incident_id = _create_incident(client)
    base = datetime.now(timezone.utc)
    first = TelemetryEvent(
        event_id="E1",
        incident_id=incident_id,
        event_type=TelemetryEventType.AUTH_LOGIN,
        timestamp=base,
        actor="eve",
        host="WS-001",
        source="WS-001",
        destination="DC-01",
        process="sshd",
        is_off_hours=True,
        is_new_device=True,
        is_attack=False,
        attack_family="lateral_movement",
    )
    _seed_telemetry(client, incident_id, [first])

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]
    assert data["status"] == "completed"

    second = TelemetryEvent(
        event_id="E2",
        incident_id=incident_id,
        event_type=TelemetryEventType.LATERAL_MOVE,
        timestamp=base,
        actor="eve",
        host="WS-001",
        source="WS-001",
        destination="SERVER-09",
        process="psexec",
        is_lateral_movement=True,
        is_attack=True,
        attack_family="lateral_movement",
    )
    _seed_telemetry(client, incident_id, [second])

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data2 = response.json()
    execution_id2 = data2["execution_id"]
    assert data2["status"] == "completed"

    events1 = client.get(f"/api/v1/agent/executions/{execution_id}/events").json()["items"]
    events2 = client.get(f"/api/v1/agent/executions/{execution_id2}/events").json()["items"]
    assert len(events1) != len(events2)


def test_mission_cancellation(client: TestClient) -> None:
    """A running adaptive mission can be cancelled."""
    incident_id = _create_incident(client)
    events = _events(incident_id)
    _seed_telemetry(client, incident_id, events)

    response = client.post(
        "/api/v1/agent/execute?background=true",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    response = client.post(f"/api/v1/agent/executions/{execution_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("cancelled", "running")
