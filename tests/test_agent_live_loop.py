"""Tests for the live, reasoning-aware agent loop and its API surface."""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


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
            "title": "Live loop test",
            "severity": "high",
            "attack_family": "lateral_movement",
            "host": "WS-001",
            "user": "eve",
        },
    )
    assert response.status_code == 200
    return response.json()["incident_id"]


def test_reasoning_events_emitted(client: TestClient) -> None:
    incident_id = _create_incident(client)
    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]
    assert data["status"] in ("completed", "failed")

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    events = response.json()["items"]
    types = [e["type"] for e in events]

    assert "agent.reasoning_started" in types
    assert "agent.reasoning_delta" in types
    assert "agent.reasoning_completed" in types
    assert "agent.decision_started" in types
    assert "agent.tool_requested" in types
    assert "agent.observation_created" in types


def test_execution_context_endpoint(client: TestClient) -> None:
    incident_id = _create_incident(client)
    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
    assert response.status_code == 200
    context = response.json()

    assert context["execution_id"] == execution_id
    assert context["status"] in ("completed", "failed")
    assert len(context["plan"]) > 0
    assert isinstance(context["observations"], list)
    assert context["reasoning_summary"]
    assert "current_action" in context


def test_stream_with_after_parameter(client: TestClient) -> None:
    incident_id = _create_incident(client)
    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    events = response.json()["items"]
    after = events[-1]["sequence"]

    with client.stream(
        "GET", f"/api/v1/agent/executions/{execution_id}/stream?after={after}"
    ) as stream:
        assert stream.status_code == 200
        assert "text/event-stream" in stream.headers.get("content-type", "")

        chunks = []
        for chunk in stream.iter_text():
            chunks.append(chunk)
            if len(chunks) > 2:
                break

        joined = "".join(chunks)
        assert ":ok" in joined
        assert "event: close" in joined or ":ok" in joined


def test_message_endpoint_creates_context_or_appends(client: TestClient) -> None:
    incident_id = _create_incident(client)
    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    response = client.post(
        f"/api/v1/agent/executions/{execution_id}/message",
        json={"message": "only get_incident"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["execution_id"] == execution_id

    response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
    assert response.status_code == 200
    context = response.json()
    assert any(m.get("content") == "only get_incident" for m in context["messages"])


def test_cancel_background_execution(client: TestClient) -> None:
    incident_id = _create_incident(client)

    response = client.post(
        "/api/v1/agent/execute?background=true",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]
    assert data["status"] == "running"

    for _ in range(20):
        context_response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
        if context_response.status_code == 200:
            break
        time.sleep(0.05)
    assert context_response.status_code == 200

    cancel_response = client.post(f"/api/v1/agent/executions/{execution_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["ok"] is True

    for _ in range(30):
        context_response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
        context = context_response.json()
        if context.get("status") == "cancelled":
            break
        time.sleep(0.05)

    assert context_response.json()["status"] == "cancelled"

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    types = [e["type"] for e in response.json()["items"]]
    assert "agent.execution_interrupted" in types


def test_background_execution_can_receive_message(client: TestClient) -> None:
    incident_id = _create_incident(client)

    response = client.post(
        "/api/v1/agent/execute?background=true",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    for _ in range(20):
        context_response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
        if context_response.status_code == 200:
            break
        time.sleep(0.05)

    message_response = client.post(
        f"/api/v1/agent/executions/{execution_id}/message",
        json={"message": "cancel"},
    )
    assert message_response.status_code == 200

    for _ in range(30):
        context_response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
        if context_response.json().get("status") in ("cancelled", "completed", "failed"):
            break
        time.sleep(0.05)

    final_status = context_response.json()["status"]
    assert final_status in ("cancelled", "completed", "failed")


def test_plan_update_message_is_stored(client: TestClient) -> None:
    incident_id = _create_incident(client)

    response = client.post(
        "/api/v1/agent/execute?background=true",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    for _ in range(20):
        context_response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
        if context_response.status_code == 200:
            break
        time.sleep(0.05)

    response = client.post(
        f"/api/v1/agent/executions/{execution_id}/message",
        json={"message": "skip get_telemetry"},
    )
    assert response.status_code == 200

    context_response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
    context = context_response.json()
    assert any(m.get("content") == "skip get_telemetry" for m in context["messages"])
