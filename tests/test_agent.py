"""Tests for the agentic execution layer."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def client():
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


def test_list_tools(client):
    response = client.get("/api/v1/agent/tools")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    names = {t["name"] for t in data["items"]}
    assert "get_incident" in names
    assert "run_replay" in names
    assert "seal_incident" in names


def test_validate_tool_inputs(client):
    response = client.post(
        "/api/v1/agent/tools/get_incident/validate",
        json={"incident_id": "INC-123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True


def test_validate_missing_input(client):
    response = client.post(
        "/api/v1/agent/tools/get_incident/validate",
        json={},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("incident_id" in e for e in data["errors"])


def test_execute_agent_without_incident(client):
    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": "Investigate something"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert "incident" in data["result_summary"].lower()


def test_execute_full_investigation(client):
    response = client.post(
        "/api/v1/incidents",
        json={
            "title": "Agent test incident",
            "severity": "high",
            "attack_family": "lateral_movement",
            "host": "WS-001",
            "user": "eve",
        },
    )
    assert response.status_code == 200
    incident = response.json()
    incident_id = incident["incident_id"]

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate missed incident {incident_id}"},
    )
    assert response.status_code == 200
    data = response.json()
    execution_id = data["execution_id"]
    assert data["status"] in ("completed", "failed")

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    events_data = response.json()
    assert "items" in events_data
    assert events_data["count"] > 0

    events = events_data["items"]
    types = [e["type"] for e in events]
    assert "agent.started" in types
    assert "agent.plan_created" in types
    assert any(e["type"] == "tool.completed" for e in events)

    completed = [e for e in events if e["type"] == "tool.completed"]
    for event in completed:
        assert event["provider"] in ("anvaya", "anvaya-local-fixture", "anvaya-local-handler")


def test_execution_polling(client):
    response = client.post(
        "/api/v1/incidents",
        json={"title": "Poll test", "severity": "low"},
    )
    assert response.status_code == 200
    incident_id = response.json()["incident_id"]

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    after = 0
    for _ in range(5):
        response = client.get(f"/api/v1/agent/executions/{execution_id}/events?after={after}")
        assert response.status_code == 200
        data = response.json()
        if data["count"] == 0:
            break
        new_events = data["items"]
        assert all(e["sequence"] > after for e in new_events)
        after = new_events[-1]["sequence"]


def test_list_profiles(client):
    response = client.get("/api/v1/agent/profiles")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    ids = {p["id"] for p in data["items"]}
    assert "sentinel" in ids
    assert "pathfinder" in ids
    assert all(p["status"] == "active" for p in data["items"])


def test_list_models(client):
    response = client.get("/api/v1/agent/models")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    by_id = {m["id"]: m for m in data["items"]}
    assert "anvaya/local-policy" in by_id
    assert by_id["anvaya/local-policy"]["availability"] == "available"
    assert by_id["agentrouter/gpt-5.6-sol"]["availability"] == "unavailable"


def test_execute_emits_agent_messages(client):
    response = client.post(
        "/api/v1/incidents",
        json={"title": "Message test", "severity": "high", "attack_family": "lateral_movement"},
    )
    assert response.status_code == 200
    incident_id = response.json()["incident_id"]

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    response = client.get(f"/api/v1/agent/executions/{execution_id}/events")
    assert response.status_code == 200
    events = response.json()["items"]
    types = [e["type"] for e in events]
    assert "agent.message" in types

    messages = [e for e in events if e["type"] == "agent.message"]
    assert len(messages) > 0
    assert all(m["label"] for m in messages)


def test_execute_stream(client):
    response = client.post(
        "/api/v1/incidents",
        json={"title": "Stream test", "severity": "high", "attack_family": "lateral_movement"},
    )
    assert response.status_code == 200
    incident_id = response.json()["incident_id"]

    response = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    )
    assert response.status_code == 200
    execution_id = response.json()["execution_id"]

    with client.stream("GET", f"/api/v1/agent/executions/{execution_id}/stream") as response:
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        chunks = []
        for chunk in response.iter_text():
            chunks.append(chunk)
            if len(chunks) > 2:
                break

        assert chunks
        joined = "".join(chunks)
        assert "data:" in joined
        assert "agent.started" in joined or "tool.completed" in joined
